using System;
using System.Collections.Concurrent;
using System.Threading;
using Autodesk.Revit.UI;

namespace Archagent.Revit
{
    /// <summary>
    /// The bridge between the HTTP listener and Revit.
    ///
    /// The Revit API may only be touched on Revit's own thread, and only inside
    /// an API context. The listener runs on a thread pool thread, so every
    /// request is queued here, raised as an <see cref="ExternalEvent"/>, and the
    /// caller blocks until Revit has run it and put the answer back.
    ///
    /// This is the single most important class in the add-in: get it wrong and
    /// Revit crashes rather than returning an error.
    /// </summary>
    internal sealed class RevitExecutor : IExternalEventHandler
    {
        private sealed class WorkItem
        {
            public Func<UIApplication, object> Work;
            public object Result;
            public Exception Error;
            public readonly ManualResetEventSlim Done = new ManualResetEventSlim(false);
        }

        private readonly ConcurrentQueue<WorkItem> _queue = new ConcurrentQueue<WorkItem>();
        private ExternalEvent _event;

        public void Attach() => _event = ExternalEvent.Create(this);

        public void Detach()
        {
            _event?.Dispose();
            _event = null;
        }

        /// <summary>Run <paramref name="work"/> on Revit's thread and wait for it.</summary>
        public object Run(Func<UIApplication, object> work, TimeSpan timeout)
        {
            if (_event == null)
                throw new InvalidOperationException("the Archagent host is not running");

            var item = new WorkItem { Work = work };
            _queue.Enqueue(item);
            _event.Raise();

            if (!item.Done.Wait(timeout))
                throw new TimeoutException(
                    "Revit did not run the command in time. It is usually busy with a modal " +
                    "dialog or a long operation - close the dialog and retry.");

            if (item.Error != null)
                throw item.Error;
            return item.Result;
        }

        // Called by Revit, on Revit's thread, in an API context.
        public void Execute(UIApplication app)
        {
            while (_queue.TryDequeue(out var item))
            {
                try
                {
                    item.Result = item.Work(app);
                }
                catch (Exception error)
                {
                    item.Error = error;
                }
                finally
                {
                    item.Done.Set();
                }
            }
        }

        public string GetName() => "Archagent host executor";
    }
}
