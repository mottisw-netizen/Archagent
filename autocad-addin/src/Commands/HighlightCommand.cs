using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;

namespace Archagent.Acad.Commands
{
    /// <summary>
    /// Show the architect what changed: select the elements of the change set
    /// in the current view. Same role as the Revit host's HighlightCommand -
    /// no transaction, no plan, nothing that can alter the model.
    /// </summary>
    internal static class HighlightCommand
    {
        public static Dictionary<string, object> Run(Document doc, Dictionary<string, object> request)
        {
            var requested = Json.List(request, "ids")
                .Select(value => value?.ToString() ?? string.Empty)
                .Where(value => value.Length > 0)
                .ToList();

            var found = new List<ObjectId>();
            var unknown = new List<object>();
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                foreach (string handleHex in requested)
                {
                    try
                    {
                        var entity = QueryCommands.Resolve(tr, doc.Database, handleHex);
                        found.Add(entity.ObjectId);
                    }
                    catch (HostException)
                    {
                        // A change set can name an entity since deleted; report
                        // it rather than refuse the whole call for it.
                        unknown.Add(handleHex);
                    }
                }
                tr.Commit();
            }

            if (found.Count > 0)
            {
                doc.Editor.SetImpliedSelection(found.ToArray());
                doc.Editor.UpdateScreen();
            }

            return new Dictionary<string, object>
                { { "selected", found.Count }, { "unknown", unknown } };
        }
    }
}
