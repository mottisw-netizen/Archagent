using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;

namespace Archagent.Acad
{
    /// <summary>
    /// JSON, using the serializer that ships with .NET Framework.
    ///
    /// Whichever host this loads into may carry its own Newtonsoft.Json; an
    /// add-in that brings a second copy is a well-known way to crash the host
    /// or break another add-in. This avoids the whole class of problem.
    /// </summary>
    internal static class Json
    {
        private static readonly JavaScriptSerializer Serializer =
            new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 };

        public static string Write(object value) => Serializer.Serialize(value);

        public static Dictionary<string, object> Read(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) return new Dictionary<string, object>();
            var parsed = Serializer.DeserializeObject(text) as Dictionary<string, object>;
            return parsed ?? new Dictionary<string, object>();
        }

        public static string String(Dictionary<string, object> data, string key, string fallback)
        {
            if (data != null && data.TryGetValue(key, out var value) && value != null)
                return Convert.ToString(value);
            return fallback;
        }

        public static double Number(Dictionary<string, object> data, string key, double fallback)
        {
            if (data != null && data.TryGetValue(key, out var value) && value != null)
            {
                try { return Convert.ToDouble(value); }
                catch (Exception) { return fallback; }
            }
            return fallback;
        }

        public static Dictionary<string, object> Dict(Dictionary<string, object> data, string key)
        {
            if (data != null && data.TryGetValue(key, out var value))
                return value as Dictionary<string, object> ?? new Dictionary<string, object>();
            return new Dictionary<string, object>();
        }

        public static List<object> List(Dictionary<string, object> data, string key)
        {
            if (data != null && data.TryGetValue(key, out var value))
            {
                if (value is object[] array) return new List<object>(array);
                if (value is List<object> list) return list;
            }
            return new List<object>();
        }

        public static string Describe(Dictionary<string, object> data) => Write(data);
    }
}
