using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace Archagent.Revit.Commands
{
    /// <summary>
    /// Show the architect what changed: select the elements of the change set in
    /// the active view.
    ///
    /// Selection is not a document edit - it changes what is highlighted, not
    /// what is stored - so this is the one write-shaped endpoint that needs no
    /// transaction and no approved plan. Nothing here can alter the model, which
    /// is why it is safe to call straight after a run.
    /// </summary>
    internal static class HighlightCommand
    {
        public static Dictionary<string, object> Run(
            UIApplication app, Document doc, Dictionary<string, object> request)
        {
            var requested = Json.List(request, "ids")
                .Select(value => value == null ? string.Empty : value.ToString())
                .Where(value => value.Length > 0)
                .ToList();

            var found = new List<ElementId>();
            var unknown = new List<object>();
            foreach (string uniqueId in requested)
            {
                // A change set can name an element the user has since deleted;
                // that is worth reporting, not worth refusing the whole call for.
                Element element = doc.GetElement(uniqueId);
                if (element == null) unknown.Add(uniqueId);
                else found.Add(element.Id);
            }

            UIDocument uiDoc = app?.ActiveUIDocument;
            if (uiDoc != null && found.Count > 0)
            {
                uiDoc.Selection.SetElementIds(found);
                uiDoc.ShowElements(found);
            }

            return new Dictionary<string, object>
            {
                { "selected", found.Count },
                { "unknown", unknown },
            };
        }
    }
}
