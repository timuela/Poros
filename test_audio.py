import subprocess

def test_get_set():
    get_code = r"""
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDevice {
    int a();
    int o();
    int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceEnumerator {
    int f();
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
public class MMDeviceEnumeratorComObject { }
public class AudioHelper {
    public static string GetDefaultAudioEndpoint() {
        var enumerator = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator;
        IMMDevice dev = null;
        enumerator.GetDefaultAudioEndpoint(0, 0, out dev);
        string id = null;
        dev.GetId(out id);
        return id;
    }
}
"@
[AudioHelper]::GetDefaultAudioEndpoint()
"""
    output = subprocess.check_output(['powershell', '-NoProfile', '-Command', get_code], text=True).strip()
    print("Default Device ID:", output)
    
    set_code = f"""
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")]
internal class _CPolicyConfigClient {{ }}
[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("F8679F50-850A-41CF-9C72-430F290290C8")]
internal interface IPolicyConfig {{
    int a(); int b(); int c(); int d(); int e(); int f(); int g(); int h(); int i(); int j();
    int SetDefaultEndpoint(string wszDeviceId, uint role);
    int SetEndpointVisibility(string wszDeviceId, bool bVisible);
}}
public class PolicyConfigClient {{
    public static void SetDefaultDevice(string deviceID) {{
        IPolicyConfig policyConfig = (IPolicyConfig)new _CPolicyConfigClient();
        policyConfig.SetDefaultEndpoint(deviceID, 0);
        policyConfig.SetDefaultEndpoint(deviceID, 1);
        policyConfig.SetDefaultEndpoint(deviceID, 2);
    }}
}}
"@
[PolicyConfigClient]::SetDefaultDevice('{output}')
"""
    subprocess.run(['powershell', '-NoProfile', '-Command', set_code], check=True)
    print("Set back successfully.")

if __name__ == '__main__':
    test_get_set()
