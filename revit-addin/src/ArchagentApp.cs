using System;
using System.IO;
using System.Reflection;
using System.Windows.Media.Imaging;
using Autodesk.Revit.UI;

namespace Archagent.Revit
{
    /// <summary>
    /// The add-in itself: a ribbon button that starts and stops the host.
    ///
    /// Nothing runs until the architect starts it. There is no background
    /// service, no auto-connect to anything remote, and the listener binds to
    /// loopback only - the agent has to be running on the same machine.
    /// </summary>
    public sealed class ArchagentApp : IExternalApplication
    {
        internal static ArchagentApp Instance { get; private set; }

        private readonly RevitExecutor _executor = new RevitExecutor();
        private HostServer _server;
        private PushButton _button;

        public int Port { get; private set; } = 8735;
        public string Token { get; private set; } = string.Empty;

        public Result OnStartup(UIControlledApplication application)
        {
            Instance = this;
            _executor.Attach();
            LoadSettings();

            const string tab = "Archagent";
            try { application.CreateRibbonTab(tab); }
            catch (Exception) { /* the tab already exists */ }

            var panel = application.CreateRibbonPanel(tab, "Permit review");
            var data = new PushButtonData(
                "ArchagentToggle", "Start\nhost",
                Assembly.GetExecutingAssembly().Location,
                typeof(ToggleHostCommand).FullName)
            {
                ToolTip = "Let Archagent read and correct this model",
                LongDescription =
                    "Starts a local bridge on http://127.0.0.1:" + Port + " that the " +
                    "Archagent permit agent uses to read the model, measure it and apply " +
                    "approved corrections. Nothing is changed without a plan you approved, " +
                    "and every plan is applied as a single undo step.",
            };
            _button = panel.AddItem(data) as PushButton;
            SetIcon(_button);
            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            _server?.Stop();
            _executor.Detach();
            return Result.Succeeded;
        }

        internal bool Running => _server != null && _server.Running;

        internal string Toggle()
        {
            if (Running)
            {
                _server.Stop();
                UpdateButton(false);
                return "Archagent host stopped.";
            }

            _server = new HostServer(_executor, Port, Token);
            _server.Start();
            UpdateButton(true);
            return "Archagent host listening on http://127.0.0.1:" + Port +
                   " (protocol " + Protocol.Version + ").";
        }

        private void UpdateButton(bool running)
        {
            if (_button == null) return;
            _button.ItemText = running ? "Stop\nhost" : "Start\nhost";
        }

        /// <summary>
        /// Port and token come from %APPDATA%\Archagent\host.json when present,
        /// so a firm can standardise them without editing the assembly.
        /// </summary>
        private void LoadSettings()
        {
            try
            {
                string path = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "Archagent", "host.json");
                if (!File.Exists(path)) return;

                var settings = Json.Read(File.ReadAllText(path));
                Port = (int)Json.Number(settings, "port", Port);
                Token = Json.String(settings, "token", Token);
            }
            catch (Exception)
            {
                // Bad settings must not stop Revit from loading the add-in.
            }
        }

        private static void SetIcon(PushButton button)
        {
            if (button == null) return;
            try
            {
                string folder = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                string icon = Path.Combine(folder ?? ".", "archagent32.png");
                if (File.Exists(icon))
                    button.LargeImage = new BitmapImage(new Uri(icon));
            }
            catch (Exception)
            {
                // An add-in without an icon still works.
            }
        }
    }

    [Autodesk.Revit.Attributes.Transaction(Autodesk.Revit.Attributes.TransactionMode.Manual)]
    public sealed class ToggleHostCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message,
            Autodesk.Revit.DB.ElementSet elements)
        {
            try
            {
                string status = ArchagentApp.Instance.Toggle();
                TaskDialog.Show("Archagent", status);
                return Result.Succeeded;
            }
            catch (Exception error)
            {
                message = error.Message;
                return Result.Failed;
            }
        }
    }
}
