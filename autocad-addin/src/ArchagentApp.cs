using System;
using System.IO;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;

[assembly: ExtensionApplication(typeof(Archagent.Acad.ArchagentApp))]
[assembly: CommandClass(typeof(Archagent.Acad.ArchagentApp))]

namespace Archagent.Acad
{
    /// <summary>
    /// The add-in itself: two commands that start and stop the host.
    ///
    /// Nothing runs until the architect types <c>ARCHAGENT</c>. There is no
    /// background service, no auto-connect to anything remote, and the
    /// listener binds to loopback only - the agent has to be running on the
    /// same machine. Same posture as the Revit add-in; a command instead of a
    /// ribbon button is the more usual way to expose this in AutoCAD, though a
    /// ribbon panel can be added the same way later without touching the host.
    /// </summary>
    public sealed class ArchagentApp : IExtensionApplication
    {
        private readonly AcadExecutor _executor = new AcadExecutor();
        private HostServer _server;

        public int Port { get; private set; } = 8736;
        public string Token { get; private set; } = string.Empty;

        public void Initialize()
        {
            LoadSettings();
            var doc = Application.DocumentManager.MdiActiveDocument;
            doc?.Editor.WriteMessage(
                "\nArchagent is loaded. Type ARCHAGENT to start or stop the review host.\n");
        }

        public void Terminate()
        {
            _server?.Stop();
        }

        [CommandMethod("ARCHAGENT")]
        public void Toggle()
        {
            var editor = Application.DocumentManager.MdiActiveDocument.Editor;
            if (_server != null && _server.Running)
            {
                _server.Stop();
                editor.WriteMessage("\nArchagent host stopped.\n");
                return;
            }

            _server = new HostServer(_executor, Port, Token);
            _server.Start();
            editor.WriteMessage("\nArchagent host listening on http://127.0.0.1:" + Port +
                " (protocol " + Protocol.Version + ").\n");
        }

        /// <summary>
        /// Port and token come from %APPDATA%\Archagent\host_acad.json when
        /// present, so a firm can standardise them without editing the DLL -
        /// a separate file from the Revit add-in's, since both may run on the
        /// same machine on different ports.
        /// </summary>
        private void LoadSettings()
        {
            try
            {
                string path = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "Archagent", "host_acad.json");
                if (!File.Exists(path)) return;

                var settings = Json.Read(File.ReadAllText(path));
                Port = (int)Json.Number(settings, "port", Port);
                Token = Json.String(settings, "token", Token);
            }
            catch (Exception)
            {
                // Bad settings must not stop AutoCAD from loading the add-in.
            }
        }
    }
}
