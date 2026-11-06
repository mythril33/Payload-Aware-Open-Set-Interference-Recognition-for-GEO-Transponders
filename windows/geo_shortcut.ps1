# geo_shortcut.ps1 - Unicode-safe .lnk shortcuts (dot-sourced by install.ps1 and the test harness).
#
# WScript.Shell's CreateShortcut()/Save() passes the .lnk path through the system ANSI code page with
# best-fit mapping: on a cp1252 Windows "GEO Pilot Ba<s-cedilla>lat" is saved as "GEO Pilot Baslat",
# and a non-ASCII user profile in the path is mangled the same way. IShellLinkW + IPersistFile are
# Unicode end to end. Windows PowerShell 5.1 and PowerShell 7 compatible; ASCII only.

$script:GeoShellLinkSource = @'
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace GeoWorkbench
{
    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellLinkW
    {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cch, IntPtr pfd, uint fFlags);
        void GetIDList(out IntPtr ppidl);
        void SetIDList(IntPtr pidl);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cch);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cch);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cch);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
        void GetHotkey(out short pwHotkey);
        void SetHotkey(short wHotkey);
        void GetShowCmd(out int piShowCmd);
        void SetShowCmd(int iShowCmd);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cch, out int piIcon);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
        void Resolve(IntPtr hwnd, uint fFlags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
    }

    [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPersistFile
    {
        void GetClassID(out Guid pClassID);
        [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, [MarshalAs(UnmanagedType.Bool)] bool fRemember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
    }

    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    class CShellLink { }

    public static class ShellLink
    {
        public static void Create(string lnkPath, string target, string workingDirectory, string description)
        {
            IShellLinkW link = (IShellLinkW)new CShellLink();
            link.SetPath(target);
            link.SetWorkingDirectory(workingDirectory);
            link.SetDescription(description);
            ((IPersistFile)link).Save(lnkPath, true);
        }

        public static string[] Read(string lnkPath)
        {
            IShellLinkW link = (IShellLinkW)new CShellLink();
            ((IPersistFile)link).Load(lnkPath, 0);
            StringBuilder target = new StringBuilder(32768);
            link.GetPath(target, target.Capacity, IntPtr.Zero, 0x4);
            StringBuilder directory = new StringBuilder(32768);
            link.GetWorkingDirectory(directory, directory.Capacity);
            return new string[] { target.ToString(), directory.ToString() };
        }
    }
}
'@

function Initialize-GeoShellLink {
    if (-not ('GeoWorkbench.ShellLink' -as [type])) {
        Add-Type -TypeDefinition $script:GeoShellLinkSource -Language CSharp
    }
}

function New-GeoShortcut {
    param([string]$LnkPath, [string]$Target, [string]$WorkingDirectory, [string]$Description)
    Initialize-GeoShellLink
    [GeoWorkbench.ShellLink]::Create($LnkPath, $Target, $WorkingDirectory, $Description)
}

# Returns @{ Target = ...; WorkingDirectory = ... } read back through the same Unicode interface.
function Read-GeoShortcut {
    param([string]$LnkPath)
    Initialize-GeoShellLink
    $values = [GeoWorkbench.ShellLink]::Read($LnkPath)
    return @{ Target = $values[0]; WorkingDirectory = $values[1] }
}
