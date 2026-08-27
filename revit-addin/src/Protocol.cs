namespace Archagent.Revit
{
    /// <summary>
    /// The wire contract, mirrored from <c>src/archagent/drawing/protocol.py</c>.
    /// The Python side and this file must agree; the mock host in
    /// <c>archagent.drawing.mock_host</c> is the executable specification both
    /// implementations are tested against.
    /// </summary>
    internal static class Protocol
    {
        public const string Version = "1.1";

        public const string Health = "/health";
        public const string Find = "/find";
        public const string Element = "/element";
        public const string Geometry = "/geometry";
        public const string Properties = "/properties";
        public const string Sheets = "/sheets";
        public const string Measure = "/measure";
        public const string Distance = "/distance";
        public const string Overlap = "/overlap";
        public const string Clearance = "/clearance";
        public const string Begin = "/transaction/begin";
        public const string Commit = "/transaction/commit";
        public const string Rollback = "/transaction/rollback";
        public const string Apply = "/apply";
        public const string Export = "/export";
        public const string SaveAs = "/save_as";
        public const string Changes = "/changes";
        public const string Highlight = "/highlight";

        // actions
        public const string Move = "move";
        public const string Resize = "resize";
        public const string Rotate = "rotate";
        public const string Delete = "delete";
        public const string Create = "create";
        public const string SetText = "set_text";
        public const string SetParameter = "set_parameter";
        public const string UpdateDimension = "update_dimension";
        public const string UpdateSchedule = "update_schedule";

        // errors
        public const string ErrNotFound = "element_not_found";
        public const string ErrAmbiguous = "ambiguous";
        public const string ErrUnsupported = "unsupported";
        public const string ErrNoTransaction = "no_transaction";
        public const string ErrReadOnly = "read_only";
        public const string ErrHost = "host_error";
        public const string ErrMeasurement = "measurement_failed";
        public const string ErrBusy = "document_busy";
    }

    /// <summary>An error the driver can map to one of its exception types.</summary>
    internal sealed class HostException : System.Exception
    {
        public string Code { get; }
        public object[] Candidates { get; }

        public HostException(string code, string message, object[] candidates = null)
            : base(message)
        {
            Code = code;
            Candidates = candidates;
        }

        public static HostException NotFound(string id) =>
            new HostException(Protocol.ErrNotFound, "element not found: '" + id + "'");

        public static HostException Unsupported(string what) =>
            new HostException(Protocol.ErrUnsupported, what);

        public static HostException NoTransaction() =>
            new HostException(Protocol.ErrNoTransaction,
                "mutation attempted outside an approved plan");
    }
}
