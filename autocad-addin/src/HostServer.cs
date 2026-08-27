using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using Autodesk.AutoCAD.ApplicationServices;
using Archagent.Acad.Commands;

namespace Archagent.Acad
{
    /// <summary>
    /// The protocol, served on loopback - identical shape to
    /// <c>revit-addin/src/HostServer.cs</c>. Every request is handled on a
    /// listener thread, marshalled onto AutoCAD's thread by
    /// <see cref="AcadExecutor"/>, and answered as JSON. The listener binds to
    /// 127.0.0.1 only: a local bridge for the architect's own machine, not a
    /// network service.
    /// </summary>
    internal sealed class HostServer
    {
        private readonly AcadExecutor _executor;
        private readonly string _token;
        private HttpListener _listener;
        private Thread _thread;

        public int Port { get; }
        public bool Running => _listener != null && _listener.IsListening;

        public HostServer(AcadExecutor executor, int port, string token)
        {
            _executor = executor;
            Port = port;
            _token = token ?? string.Empty;
        }

        public void Start()
        {
            if (Running) return;
            _listener = new HttpListener();
            _listener.Prefixes.Add("http://127.0.0.1:" + Port + "/");
            _listener.Start();
            _thread = new Thread(Loop) { IsBackground = true, Name = "archagent-acad-host" };
            _thread.Start();
        }

        public void Stop()
        {
            try { _listener?.Stop(); } catch (Exception) { }
            _listener = null;
        }

        private void Loop()
        {
            while (Running)
            {
                HttpListenerContext context;
                try { context = _listener.GetContext(); }
                catch (Exception) { return; }   // the listener was stopped
                ThreadPool.QueueUserWorkItem(_ => Handle(context));
            }
        }

        private void Handle(HttpListenerContext context)
        {
            string path = context.Request.Url.AbsolutePath;
            try
            {
                if (_token.Length > 0 &&
                    context.Request.Headers["X-Archagent-Token"] != _token)
                {
                    Respond(context, 403, new Dictionary<string, object>
                        { { "error", Protocol.ErrHost }, { "message", "bad token" } });
                    return;
                }

                string body;
                using (var reader = new StreamReader(context.Request.InputStream,
                           context.Request.ContentEncoding ?? Encoding.UTF8))
                    body = reader.ReadToEnd();

                var request = Json.Read(body);
                // AutoCAD's thread runs the work; this thread waits for the answer.
                var result = _executor.Run(doc => Route(doc, path, request),
                    TimeSpan.FromSeconds(180));
                Respond(context, 200, result);
            }
            catch (HostException error)
            {
                var payload = new Dictionary<string, object>
                    { { "error", error.Code }, { "message", error.Message } };
                if (error.Candidates != null) payload["candidates"] = error.Candidates;
                Respond(context, StatusFor(error.Code), payload);
            }
            catch (TimeoutException error)
            {
                Respond(context, 503, new Dictionary<string, object>
                    { { "error", Protocol.ErrBusy }, { "message", error.Message } });
            }
            catch (Exception error)
            {
                Respond(context, 500, new Dictionary<string, object>
                    { { "error", Protocol.ErrHost }, { "message", error.ToString() } });
            }
        }

        private static int StatusFor(string code)
        {
            switch (code)
            {
                case Protocol.ErrNotFound: return 404;
                case Protocol.ErrAmbiguous: return 409;
                case Protocol.ErrReadOnly:
                case Protocol.ErrNoTransaction:
                case Protocol.ErrUnsupported: return 400;
                default: return 400;
            }
        }

        /// <summary>Runs on AutoCAD's thread, with the document locked.</summary>
        private static object Route(Document doc, string path, Dictionary<string, object> request)
        {
            if (doc == null && path != Protocol.Health)
                throw new HostException(Protocol.ErrHost, "no document is open in AutoCAD");

            switch (path)
            {
                case Protocol.Health: return QueryCommands.Health(doc);
                case Protocol.Find: return QueryCommands.Find(doc, request);
                case Protocol.Element: return QueryCommands.Element(doc, request);
                case Protocol.Geometry: return QueryCommands.Geometry(doc, request);
                case Protocol.Properties: return QueryCommands.Properties(doc, request);
                case Protocol.Sheets: return QueryCommands.Sheets(doc);
                case Protocol.Measure: return MeasureCommand.Run(doc, request);
                case Protocol.Distance: return DistanceCommand.Distance(doc, request);
                case Protocol.Overlap: return DistanceCommand.Overlap(doc, request);
                case Protocol.Clearance: return DistanceCommand.Clearance(doc, request);
                case Protocol.Apply: return ApplyCommand.Run(doc, request);
                case Protocol.Changes: return ApplyCommand.Changes(request);
                case Protocol.Highlight: return HighlightCommand.Run(doc, request);
                case Protocol.Export: return ExportCommand.Run(doc, request);
                case Protocol.SaveAs: return ExportCommand.SaveAs(doc, request);
                case Protocol.Begin:
                case Protocol.Commit:
                case Protocol.Rollback:
                    // A transaction cannot be held open between separate HTTP
                    // requests here either, for the same reason as the Revit
                    // host: this host implements the batch form of /apply.
                    throw HostException.Unsupported(
                        "this host applies a plan in one /apply call; per-action " +
                        "transactions are not available");
                default:
                    throw HostException.Unsupported("unknown endpoint: " + path);
            }
        }

        private static void Respond(HttpListenerContext context, int status, object payload)
        {
            try
            {
                byte[] body = Encoding.UTF8.GetBytes(Json.Write(payload));
                context.Response.StatusCode = status;
                context.Response.ContentType = "application/json; charset=utf-8";
                context.Response.ContentLength64 = body.Length;
                context.Response.OutputStream.Write(body, 0, body.Length);
                context.Response.OutputStream.Close();
            }
            catch (Exception)
            {
                // The client hung up; nothing useful to do.
            }
        }
    }
}
