using System.Collections.ObjectModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Threading;

namespace TyperX;

public static class Program
{
    [STAThread]
    public static void Main()
    {
        var app = new Application { ShutdownMode = ShutdownMode.OnMainWindowClose };
        app.Run(new MainWindow());
    }
}

public partial class MainWindow : Window
{
    private const int WmHotkey = 0x0312;
    private const int StartHotkey = 1;
    private const int StopHotkey = 2;
    private readonly ObservableCollection<TemplateModel> _templates = new();
    private readonly ObservableCollection<string> _preview = new();
    private readonly Random _random = new();
    private CancellationTokenSource? _typingCts;
    private IntPtr _windowHandle;
    private bool _loading = true;
    private bool _isTyping;

    private static readonly HashSet<string> CueWords = new(StringComparer.OrdinalIgnoreCase)
    {
        "привет", "слушай", "смотри", "короче", "ладно", "кстати", "ну", "как", "что", "чем", "где", "когда", "почему", "зачем", "кто", "я", "ты", "мы"
    };

    private static readonly Dictionary<char, string> Neighbours = new()
    {
        ['а']="пвм", ['б']="юьл", ['в']="аып", ['г']="ншр", ['д']="лжв", ['е']="кн", ['ё']="1й", ['ж']="дэж", ['з']="хщ",
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
        if (_windowHandle != IntPtr.Zero)
        {
            UnregisterHotKey(_windowHandle, StartHotkey);
            UnregisterHotKey(_windowHandle, StopHotkey);
        }
        SaveState();
        base.OnClosed(e);
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
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

    private void TemplateList_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (TemplateList.SelectedItem is not TemplateModel item) return;
        TemplateName.Text = item.Title;
        Editor.Text = item.Text;
    }

    private void NewTemplate_Click(object sender, RoutedEventArgs e)
    {
        TemplateList.SelectedItem = null;
        TemplateName.Text = "Новый шаблон";
        Editor.Clear();
        Editor.Focus();
    }

    private void SaveTemplate_Click(object sender, RoutedEventArgs e)
    {
        var title = string.IsNullOrWhiteSpace(TemplateName.Text) ? "Без названия" : TemplateName.Text.Trim();
        if (TemplateList.SelectedItem is TemplateModel selected)
        {
            selected.Title = title;
            selected.Text = Editor.Text;
            TemplateList.Items.Refresh();
        }
        else
        {
            var item = new TemplateModel { Title = title, Text = Editor.Text, IsBuiltIn = false };
            _templates.Add(item);
            TemplateList.SelectedItem = item;
        }
        SaveState();
        StatusText.Text = "Шаблон сохранён";
    }

    private void Editor_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        if (CharCount is null) return;
        CharCount.Text = $"{Editor.Text.Length} знаков";
        RefreshPreview();
    }

    private void Settings_Changed(object sender, RoutedEventArgs e)
    {
        if (_loading) return;
        RefreshSettingsLabels();
        RefreshPreview();
    }

    private void Settings_Changed(object sender, System.Windows.Controls.Primitives.DragCompletedEventArgs e) => Settings_Changed(sender, new RoutedEventArgs());

    private void RefreshSettingsLabels()
    {
        if (WpmValue is null) return;
        WpmValue.Text = $"{Math.Round(WpmSlider.Value)} WPM";
        VariationValue.Text = $"{Math.Round(VariationSlider.Value)}%";
        TypoValue.Text = $"{TypoSlider.Value:0.0}%";
    }

    private void RefreshPreview()
    {
        if (Editor is null || _preview is null) return;
        _preview.Clear();
        var seed = StringComparer.Ordinal.GetHashCode(Editor.Text ?? string.Empty);
        foreach (var part in SplitMessages(Editor.Text ?? string.Empty, new Random(seed))) _preview.Add(part);
    }

    private async void StartButton_Click(object sender, RoutedEventArgs e)
    {
        if (_isTyping || string.IsNullOrWhiteSpace(Editor.Text)) return;
        WindowState = WindowState.Minimized;
        for (var i = 3; i > 0; i--)
        {
            StatusText.Text = $"Фокус на Telegram: старт через {i}";
            await Task.Delay(1000);
        }
        var target = GetForegroundWindow();
        if (target == _windowHandle || target == IntPtr.Zero)
        {
            WindowState = WindowState.Normal;
            StatusText.Text = "Не вижу окно для ввода";
            return;
        }
        await BeginTypingAsync(target);
    }

    private void StopButton_Click(object sender, RoutedEventArgs e) => StopTyping();

    private async Task BeginTypingAsync(IntPtr target)
    {
        if (_isTyping || string.IsNullOrWhiteSpace(Editor.Text)) return;
        var plan = SmartSplitCheck.IsChecked == true
            ? SplitMessages(Editor.Text, _random)
            : Editor.Text.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
        if (plan.Count == 0) return;

        _isTyping = true;
        _typingCts = new CancellationTokenSource();
        StartButton.IsEnabled = false;
        StopButton.IsEnabled = true;
        SetForegroundWindow(target);

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
                        var wrong = GetTypo(ch);
                        SendUnicode(wrong);
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
        catch (OperationCanceledException)
        {
            StatusText.Text = "Остановлено";
        }
        finally
        {
            _isTyping = false;
            _typingCts.Dispose();
            _typingCts = null;
            StartButton.IsEnabled = true;
            StopButton.IsEnabled = false;
        }
    }

    private void StopTyping() => _typingCts?.Cancel();

    private List<string> SplitMessages(string text, Random rng)
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
                var afterAside = normalized == "например" && current.Count >= 2 && i < words.Count - 1 && rng.NextDouble() < 0.42;
                var longEnough = current.Count >= softLimit;
                if (sentenceEnd || afterAside || longEnough)
                {
                    Flush(current, result);
                    softLimit = rng.Next(5, 10);
                }
            }
            Flush(current, result);
        }

        if (KeepPunctuationCheck.IsChecked != true)
            result = result.Select(x => x.TrimEnd('.', ',', '!', '?', ':', ';', '…')).Where(x => x.Length > 0).ToList();
        return result;
    }

    private static void Flush(List<string> current, List<string> result)
    {
        if (current.Count == 0) return;
        var value = string.Join(' ', current).Trim();
        if (value.Length > 0) result.Add(value);
        current.Clear();
    }

    private bool ShouldMakeTypo(char ch) => TyposCheck.IsChecked == true && char.IsLetter(ch) &&
                                             _random.NextDouble() < TypoSlider.Value / 100.0 && Neighbours.ContainsKey(char.ToLowerInvariant(ch));

    private char GetTypo(char original)
    {
        var lower = char.ToLowerInvariant(original);
        var options = Neighbours[lower];
        var picked = options[_random.Next(options.Length)];
        return char.IsUpper(original) ? char.ToUpperInvariant(picked) : picked;
    }

    private async Task CharacterDelayAsync(char ch, CancellationToken token)
    {
        var baseMs = 60000.0 / (Math.Max(35, WpmSlider.Value) * 5.0);
        var variation = VariationSlider.Value / 100.0;
        var gaussian = Math.Sqrt(-2.0 * Math.Log(Math.Max(0.0001, _random.NextDouble()))) * Math.Cos(2.0 * Math.PI * _random.NextDouble());
        var multiplier = Math.Clamp(1.0 + gaussian * variation, 0.35, 2.4);
        if (ch == ' ') multiplier *= 0.62;
        if (PunctuationPauseCheck.IsChecked == true)
        {
            if (ch is ',' or ':' or ';') multiplier += 1.8;
            if (ch is '.' or '!' or '?' or '…') multiplier += 3.8;
        }
        var delay = (int)Math.Clamp(baseMs * multiplier, 12, 900);
        await Task.Delay(delay, token);
    }

    private Task DelayAsync(int min, int max, CancellationToken token)
    {
        var variation = VariationSlider.Value / 100.0;
        var value = _random.Next(min, max + 1);
        value = (int)(value * (1.0 + (_random.NextDouble() * 2 - 1) * variation));
        return Task.Delay(Math.Max(20, value), token);
    }

    private void LoadState()
    {
        AppState? state = null;
        try
        {
            if (File.Exists(StatePath)) state = JsonSerializer.Deserialize<AppState>(File.ReadAllText(StatePath));
        }
        catch { /* A broken local state should never block startup. */ }

        foreach (var template in state?.Templates?.Count > 0 ? state.Templates : BuiltInTemplates()) _templates.Add(template);
        if (state is null) return;
        WpmSlider.Value = state.Wpm;
        VariationSlider.Value = state.Variation;
        TypoSlider.Value = state.TypoChance;
        SmartSplitCheck.IsChecked = state.SmartSplit;
        TyposCheck.IsChecked = state.Typos;
        PunctuationPauseCheck.IsChecked = state.PunctuationPauses;
        KeepPunctuationCheck.IsChecked = state.KeepPunctuation;
    }

    private void SaveState()
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
        catch { /* Settings persistence is best effort. */ }
    }

    private static string StatePath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "TyperX", "state.json");

    private static List<TemplateModel> BuiltInTemplates() => new()
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
        new() { Title="Шахматы 5D", IsBuiltIn=true, Text="Ход неожиданный. Настолько неожиданный что даже ты похоже не понял куда пошла фигура. Но уверенность конечно чемпионская." },
        new() { Title="Спокойный финал", IsBuiltIn=true, Text="Ладно убедил. Не аргументами конечно а выносливостью. Я просто не был готов что эта мысль будет возвращаться каждый сезон." }
    };

    [DllImport("user32.dll")] private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, int vk);
    [DllImport("user32.dll")] private static extern bool UnregisterHotKey(IntPtr hWnd, int id);
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    private static void SendUnicode(char ch)
    {
        var inputs = new[]
        {
            new INPUT { type = 1, U = new InputUnion { ki = new KEYBDINPUT { wScan = ch, dwFlags = 0x0004 } } },
            new INPUT { type = 1, U = new InputUnion { ki = new KEYBDINPUT { wScan = ch, dwFlags = 0x0004 | 0x0002 } } }
        };
        SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
    }

    private static void SendVirtualKey(ushort key)
    {
        var inputs = new[]
        {
            new INPUT { type = 1, U = new InputUnion { ki = new KEYBDINPUT { wVk = key } } },
            new INPUT { type = 1, U = new InputUnion { ki = new KEYBDINPUT { wVk = key, dwFlags = 0x0002 } } }
        };
        SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
    }

    [StructLayout(LayoutKind.Sequential)] private struct INPUT { public uint type; public InputUnion U; }
    [StructLayout(LayoutKind.Explicit)] private struct InputUnion { [FieldOffset(0)] public KEYBDINPUT ki; }
    [StructLayout(LayoutKind.Sequential)] private struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public UIntPtr dwExtraInfo; }
}

public sealed class TemplateModel
{
    public string Title { get; set; } = "Шаблон";
    public string Text { get; set; } = string.Empty;
    public bool IsBuiltIn { get; set; }
}

public sealed class AppState
{
    public double Wpm { get; set; } = 110;
    public double Variation { get; set; } = 22;
    public double TypoChance { get; set; } = 1.5;
    public bool SmartSplit { get; set; } = true;
    public bool Typos { get; set; } = true;
    public bool PunctuationPauses { get; set; } = true;
    public bool KeepPunctuation { get; set; } = true;
    public List<TemplateModel> Templates { get; set; } = new();
}
