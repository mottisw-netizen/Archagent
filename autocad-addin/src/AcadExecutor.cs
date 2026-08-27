using System;
using System.Collections.Concurrent;
using System.Threading;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.ApplicationServices.Core;

namespace Archagent.Acad
{
    /// <summary>
    /// The bridge between the HTTP listener and AutoCAD.
    ///
    /// The AutoCAD API may only be touched on AutoCAD's own thread, with the
    /// document locked. The listener runs on a thread pool thread, so every
    /// request is queued here and run through
    /// <see cref="Application.DocumentManager.ExecuteInApplicationContext"/>,
    /// which marshals the callback onto AutoCAD's thread; the caller blocks
    /// until it has run and put the answer back. Same shape as
    /// <c>revit-addin/src/RevitExecutor.cs</c> - only the marshalling primitive
    /// differs between the two hosts.
    /// </summary>
    internal sealed class AcadExecutor
    {
        private sealed class WorkItem
        {
            public Func<Document, object> Work;
            public object Result;
            public Exception Error;
            public readonly ManualResetEventSlim Done = new ManualResetEventSlim(false);
        }

        private readonly ConcurrentQueue<WorkItem> _queue = new ConcurrentQueue<WorkItem>();

        /// <summary>Run <paramref name="work"/> on AutoCAD's thread, with the active document locked.</summary>
        public object Run(Func<Document, object> work, TimeSpan timeout)
        {
            var item = new WorkItem { Work = work };
            _queue.Enqueue(item);

            Application.DocumentManager.ExecuteInApplicationContext(_ =>
            {
                while (_queue.TryDequeue(out var pending))
                {
                    try
                    {
                        Document doc = Application.DocumentManager.MdiActiveDocument;
                        if (doc == null)
                        {
                            pending.Work(null);   // let Route() raise its own "no document" error
                        }
                        else
                        {
                            using (doc.LockDocument())
                                pending.Result = pending.Work(doc);
                        }
                    }
                    catch (Exception error)
                    {
                        pending.Error = error;
                    }
                    finally
                    {
                        pending.Done.Set();
                    }
                }
            }, null);

            if (!item.Done.Wait(timeout))
                throw new TimeoutException(
                    "AutoCAD did not run the command in time. It is usually busy with a modal " +
                    "dialog or a long operation - close the dialog and retry.");

            if (item.Error != null)
                throw item.Error;
            return item.Result;
        }
    }
}
