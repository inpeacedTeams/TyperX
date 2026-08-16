using System.Collections.ObjectModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;

namespace TyperX;

public static class Program
{
    [STAThread] public static void Main() => new Application { ShutdownMode = ShutdownMode.OnMainWindowClose }.Run(new MainWindow());
}

public partial class MainWindow : Window
{
    const int WmHotkey = 0x0312, StartHotkey = 1, StopHotkey = 2;
    readonly ObservableCollection<TemplateModel> _templates = new();
    readonly ObservableCollection<string> _preview = new();
    readonly Random _random = new();
    CancellationTokenSource? _typingCts;
    IntPtr _windowHandle;
    bool _loading = true, _isTyping;

    static readonly HashSet<string> CueWords = new(StringComparer.OrdinalIgnoreCase)
    { "привет", "слушай", "смотри", "короче", "ладно", "кстати", "ну", "как", "что", "чем", "где", "когда", "почему", "зачем", "кто", "я", "ты", "мы" };

    static readonly Dictionary<char, string> Neighbours = new()
    {
        ['а']="пвм", ['б']="юьл", ['в']="аып", ['г']="ншр", ['д']="лж", ['е']="кн", ['ё']="1й", ['ж']="дэ", ['з']="хщ",
        ['и']="мть", ['й']="цф", ['к']="уен", ['л']="джо", ['м']="сиа", ['н']="геп", ['о']="лр", ['п']="арн", ['р']="от",
        ['с']="мч", ['т']="ьи", ['у']="кц", ['ф']="йы", ['х']="зъ", ['ц']="уй", ['ч']="ся", ['ш']="щг", ['щ']="шз", ['ъ']="х",
        ['ы']="вф", ['ь']="тб", ['э']="ж", ['ю']="б", ['я']="чс"
    };

    public MainWindow()
    {
        InitializeComponent();
        PreviewList.ItemsSource = _preview;
        LoadState();
        TemplateList.ItemsSource = _templates;
        TemplateList.DisplayMemberPath = nameof(TemplateModel.Title);
        if (_templates.Count > 0) TemplateList.SelectedIndex = 0;
        _loading = false;
        RefreshSettingsLabels();
        RefreshPreview();
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        _windowHandle = new WindowInteropHelper(this).Handle;
        HwndSource.FromHwnd(_windowHandle)?.AddHook(WndProc);
        RegisterHotKey(_windowHandle, StartHotkey, 0, KeyInterop.VirtualKeyFromKey(Key.F8));
        RegisterHotKey(_windowHandle, StopHotkey, 0, KeyInterop.VirtualKeyFromKey(Key.F9));
    }

    protected override void OnClosed(EventArgs e)
    {
        _typingCts?.Cancel();
        if (_windowHandle != IntPtr.Zero) { UnregisterHotKey(_windowHandle, StartHotkey); UnregisterHotKey(_windowHandle, StopHotkey); }
        SaveState();
        base.OnClosed(e);
    }

    IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg != WmHotkey) return IntPtr.Zero;
        handled = true;
        if (wParam.ToInt32() == StopHotkey) StopTyping();
        if (wParam.ToInt32() == StartHotkey && !_isTyping)
        {
            var target = GetForegroundWindow();
            if (target != _windowHandle) _ = BeginTypingAsync(target);
        }
        return IntPtr.Zero;
    }

    void TemplateList_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (TemplateList.SelectedItem is not TemplateModel item) return;
        TemplateName.Text = item.Title;
        Editor.Text = item.Text;
    }

    void NewTemplate_Click(object sender, RoutedEventArgs e)
    {
        TemplateList.SelectedItem = null;
        TemplateName.Text = "Новый шаблон";
        Editor.Clear();
        Editor.Focus();
    }

    void SaveTemplate_Click(object sender, RoutedEventArgs e)
    {
        var title = string.IsNullOrWhiteSpace(TemplateName.Text) ? "Без названия" : TemplateName.Text.Trim();
        if (TemplateList.SelectedItem is TemplateModel selected)
        {
            selected.Title = title; selected.Text = Editor.Text; TemplateList.Items.Refresh();
        }
        else
        {
            var item = new TemplateModel { Title = title, Text = Editor.Text };
            _templates.Add(item); TemplateList.SelectedItem = item;
        }
        SaveState(); StatusText.Text = "Шаблон сохранён";
    }

    void Editor_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        if (CharCount is null) return;
        CharCount.Text = $"{Editor.Text.Length} знаков";
        RefreshPreview();
    }

    void Settings_Changed(object sender, RoutedEventArgs e)
    {
        if (_loading) return;
        RefreshSettingsLabels(); RefreshPreview();
    }

    void RefreshSettingsLabels()
    {
        if (WpmValue is null) return;
        WpmValue.Text = $"{Math.Round(WpmSlider.Value)} WPM";
        VariationValue.Text = $"{Math.Round(VariationSlider.Value)}%";
        TypoValue.Text = $"{TypoSlider.Value:0.0}%";
    }

    void RefreshPreview()
    {
        if (Editor is null) return;
        _preview.Clear();
        var seed = StringComparer.Ordinal.GetHashCode(Editor.Text ?? string.Empty);
        foreach (var part in SplitMessages(Editor.Text ?? string.Empty, new Random(seed))) _preview.Add(part);
    }

    async void StartButton_Click(object sender, RoutedEventArgs e)
    {
        if (_isTyping || string.IsNullOrWhiteSpace(Editor.Text)) return;
        WindowState = WindowState.Minimized;
        for (var i = 3; i > 0; i--) { StatusText.Text = $"Фокус на Telegram: старт через {i}"; await Task.Delay(1000); }
        var target = GetForegroundWindow();
        if (target == _windowHandle || target == IntPtr.Zero)
        {
            WindowState = WindowState.Normal; StatusText.Text = "Не вижу окно для ввода"; return;
        }
        await BeginTypingAsync(target);
    }

    void StopButton_Click(object sender, RoutedEventArgs e) => StopTyping();

    async Task BeginTypingAsync(IntPtr target)
    {
        if (_isTyping || string.IsNullOrWhiteSpace(Editor.Text)) return;
        var plan = SmartSplitCheck.IsChecked == true
            ? SplitMessages(Editor.Text, _random)
            : Editor.Text.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
        if (plan.Count == 0) return;

        _isTyping = true; _typingCts = new CancellationTokenSource();
        StartButton.IsEnabled = false; StopButton.IsEnabled = true; SetForegroundWindow(target);
        try
        {
            for (var messageIndex = 0; messageIndex < plan.Count; messageIndex++)
            {
                var message = plan[messageIndex];
                StatusText.Text = $"Печатаю {messageIndex + 1} из {plan.Count}";
                foreach (var ch in message)
                {
                    _typingCts.Token.ThrowIfCancellationRequested();
                    if (ShouldMakeTypo(ch))
                    {
                        SendUnicode(GetTypo(ch));
                        await DelayAsync(90, 260, _typingCts.Token);
                        SendVirtualKey(0x08);
                        await DelayAsync(70, 190, _typingCts.Token);
                    }
                    SendUnicode(ch);
                    await CharacterDelayAsync(ch, _typingCts.Token);
                }
                _typingCts.Token.ThrowIfCancellationRequested();
                await DelayAsync(180, 560, _typingCts.Token);
                SendVirtualKey(0x0D);
                if (messageIndex < plan.Count - 1)
                {
                    var thoughtBonus = message.Length > 34 ? 650 : 0;
                    await DelayAsync(620 + thoughtBonus, 1750 + thoughtBonus, _typingCts.Token);
                }
            }
            StatusText.Text = $"Готово: {plan.Count} сообщений";
        }
        catch (OperationCanceledException) { StatusText.Text = "Остановлено"; }
        finally
        {
            _isTyping = false; _typingCts.Dispose(); _typingCts = null;
            StartButton.IsEnabled = true; StopButton.IsEnabled = false;
        }
    }

    void StopTyping() => _typingCts?.Cancel();

    List<string> SplitMessages(string text, Random rng)
    {
        var result = new List<string>();
        foreach (var paragraph in Regex.Split(text.Trim(), @"\r?\n+").Where(x => !string.IsNullOrWhiteSpace(x)))
        {
            var words = Regex.Matches(paragraph, @"\S+").Select(m => m.Value).ToList();
            var current = new List<string>();
            var softLimit = rng.Next(5, 10);
            for (var i = 0; i < words.Count; i++)
            {
                var raw = words[i];
                var normalized = raw.Trim(' ', ',', '.', '!', '?', ':', ';', '…', '(', ')', '"', '\'').ToLowerInvariant();
                var cueBreak = current.Count > 0 && CueWords.Contains(normalized) &&
                    (current.Count >= 2 || normalized is "как" or "что" or "чем" or "где" or "когда" or "почему" or "зачем");
                if (cueBreak) Flush(current, result);
                current.Add(raw);
                var sentenceEnd = raw.EndsWith('.') || raw.EndsWith('!') || raw.EndsWith('?') || raw.EndsWith('…');
                var afterAside = normalized == "например" && current.Count >= 2 && i < words.Count - 1 && rng.NextDouble() < .42;
                if (sentenceEnd || afterAside || current.Count >= softLimit) { Flush(current, result); softLimit = rng.Next(5, 10); }
            }
            Flush(current, result);
        }
        if (KeepPunctuationCheck.IsChecked != true)
            result = result.Select(x => x.TrimEnd('.', ',', '!', '?', ':', ';', '…')).Where(x => x.Length > 0).ToList();
        return result;
    }

    static void Flush(List<string> current, List<string> result)
    {
        if (current.Count == 0) return;
        var value = string.Join(' ', current).Trim();
        if (value.Length > 0) result.Add(value);
        current.Clear();
    }

    bool ShouldMakeTypo(char ch) => TyposCheck.IsChecked == true && char.IsLetter(ch) &&
        _random.NextDouble() < TypoSlider.Value / 100.0 && Neighbours.ContainsKey(char.ToLowerInvariant(ch));

    char GetTypo(char original)
    {
        var options = Neighbours[char.ToLowerInvariant(original)];
        var picked = options[_random.Next(options.Length)];
        return char.IsUpper(original) ? char.ToUpperInvariant(picked) : picked;
    }

    async Task CharacterDelayAsync(char ch, CancellationToken token)
    {
        var baseMs = 60000.0 / (Math.Max(35, WpmSlider.Value) * 5.0);
        var variation = VariationSlider.Value / 100.0;
        var gaussian = Math.Sqrt(-2 * Math.Log(Math.Max(.0001, _random.NextDouble()))) * Math.Cos(2 * Math.PI * _random.NextDouble());
        var multiplier = Math.Clamp(1 + gaussian * variation, .35, 2.4);
        if (ch == ' ') multiplier *= .62;
        if (PunctuationPauseCheck.IsChecked == true)
        {
            if (ch is ',' or ':' or ';') multiplier += 1.8;
            if (ch is '.' or '!' or '?' or '…') multiplier += 3.8;
        }
        await Task.Delay((int)Math.Clamp(baseMs * multiplier, 12, 900), token);
    }

    Task DelayAsync(int min, int max, CancellationToken token)
    {
        var value = _random.Next(min, max + 1);
        value = (int)(value * (1 + (_random.NextDouble() * 2 - 1) * VariationSlider.Value / 100.0));
        return Task.Delay(Math.Max(20, value), token);
    }

    void LoadState()
    {
        AppState? state = null;
        try { if (File.Exists(StatePath)) state = JsonSerializer.Deserialize<AppState>(File.ReadAllText(StatePath)); } catch { }
        foreach (var template in state?.Templates?.Count > 0 ? state.Templates : BuiltInTemplates()) _templates.Add(template);
        if (state is null) return;
        WpmSlider.Value = state.Wpm; VariationSlider.Value = state.Variation; TypoSlider.Value = state.TypoChance;
        SmartSplitCheck.IsChecked = state.SmartSplit; TyposCheck.IsChecked = state.Typos;
        PunctuationPauseCheck.IsChecked = state.PunctuationPauses; KeepPunctuationCheck.IsChecked = state.KeepPunctuation;
    }

    void SaveState()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(StatePath)!);
            var state = new AppState
            {
                Wpm = WpmSlider.Value, Variation = VariationSlider.Value, TypoChance = TypoSlider.Value,
                SmartSplit = SmartSplitCheck.IsChecked == true, Typos = TyposCheck.IsChecked == true,
                PunctuationPauses = PunctuationPauseCheck.IsChecked == true, KeepPunctuation = KeepPunctuationCheck.IsChecked == true,
                Templates = _templates.ToList()
            };
            File.WriteAllText(StatePath, JsonSerializer.Serialize(state, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch { }
    }

    static string StatePath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "TyperX", "state.json");

    static List<TemplateModel> BuiltInTemplates() => new()
    {
        new() { Title="Разогрев", IsBuiltIn=true, Text="Привет как дела что делаешь чем занимаешься я например учу уроки." },
        new() { Title="Космический эксперт", IsBuiltIn=true, Text="Ты сейчас так уверенно это написал будто лично согласовывал законы физики с советом галактики. Подожди я записываю эту историческую мысль." },
        new() { Title="Финальный босс офиса", IsBuiltIn=true, Text="С таким серьёзным тоном обычно объявляют квартальный отчёт. А тут одна фраза и уже ощущение будто началась последняя битва с бухгалтерией." },
        new() { Title="Архив интернета", IsBuiltIn=true, Text="Не удаляй сообщение пожалуйста. Интернет должен сохранить этот момент для будущих исследователей. Они будут спорить что именно ты имел в виду." },
        new() { Title="Сверхразум", IsBuiltIn=true, Text="Секунду я пытаюсь догнать эту мысль. Она уже обогнула здравый смысл и уходит на второй круг. Кажется без карты не справлюсь." },
        new() { Title="Техническая поддержка", IsBuiltIn=true, Text="Проверил твою аргументацию. Перезагрузка не помогла. Попробуй выключить уверенность на десять секунд и включить факты." },
        new() { Title="Срочные новости", IsBuiltIn=true, Text="Срочные новости. В чате обнаружено мнение такой плотности что рядом перестал работать компас. Специалисты уже выехали." },
        new() { Title="Музейный экспонат", IsBuiltIn=true, Text="Эту переписку нельзя заканчивать. Её надо аккуратно поместить под стекло. Табличка будет называться человек был уверен до самого конца." },
        new() { Title="Режиссёрская версия", IsBuiltIn=true, Text="Постой это была полная версия мысли или только трейлер. Потому что интрига есть сюжет потерялся а продолжение почему-то уже пугает." },
        new() { Title="Шахматы 5D", IsBuiltIn=true, Text="Ход неожиданный. Настолько неожиданный что даже ты похоже не понял куда пошла фигура. Но уверенность конечно чемпионская." }
    };

    [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hWnd, int id, uint modifiers, int vk);
    [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr hWnd, int id);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint count, INPUT[] inputs, int size);

    static void SendUnicode(char ch) => SendKeyboard(new KEYBDINPUT { wScan = ch, dwFlags = 0x0004 }, new KEYBDINPUT { wScan = ch, dwFlags = 0x0006 });
    static void SendVirtualKey(ushort key) => SendKeyboard(new KEYBDINPUT { wVk = key }, new KEYBDINPUT { wVk = key, dwFlags = 0x0002 });
    static void SendKeyboard(KEYBDINPUT down, KEYBDINPUT up)
    {
        var inputs = new[] { new INPUT { type = 1, U = new InputUnion { ki = down } }, new INPUT { type = 1, U = new InputUnion { ki = up } } };
        SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
    }

    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public InputUnion U; }
    [StructLayout(LayoutKind.Explicit)] struct InputUnion
    {
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx, dy; public uint mouseData, dwFlags, time; public UIntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort wVk, wScan; public uint dwFlags, time; public UIntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] struct HARDWAREINPUT { public uint uMsg; public ushort wParamL, wParamH; }
}

public sealed class TemplateModel
{
    public string Title { get; set; } = "Шаблон";
    public string Text { get; set; } = string.Empty;
    public bool IsBuiltIn { get; set; }
}

public sealed class AppState
{
    public double Wpm { get; set; } = 110, Variation { get; set; } = 22, TypoChance { get; set; } = 1.5;
    public bool SmartSplit { get; set; } = true, Typos { get; set; } = true, PunctuationPauses { get; set; } = true, KeepPunctuation { get; set; } = true;
    public List<TemplateModel> Templates { get; set; } = new();
}
