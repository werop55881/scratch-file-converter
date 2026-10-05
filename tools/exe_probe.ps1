# Send real keys to the game exe (our own instance) and screenshot its window.
param(
    [string]$Exe = "$env:USERPROFILE\Downloads\Saves\Fighting Game-python\Fighting Game.exe",
    [string]$OutDir = "$env:TEMP\opencode\my_exe_probe"
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class K {
    public delegate bool Proc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(Proc cb, IntPtr l);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out R r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref Pt p);
    [StructLayout(LayoutKind.Sequential)] public struct Pt { public int X, Y; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
    [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint mapType);
    public static void KeyDown(IntPtr h, byte vk) {
        uint sc = MapVirtualKey(vk, 0);
        IntPtr lp = (IntPtr)(int)(0x00000001 | (sc << 16));
        PostMessage(h, 0x100, (IntPtr)vk, lp);
    }
    public static void KeyUp(IntPtr h, byte vk) {
        uint sc = MapVirtualKey(vk, 0);
        IntPtr lp = (IntPtr)(int)(0xC0000001 | (sc << 16));
        PostMessage(h, 0x101, (IntPtr)vk, lp);
    }
    [StructLayout(LayoutKind.Sequential)] public struct R { public int Left, Top, Right, Bottom; }
    public static IntPtr Find(uint[] pids) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => {
            if (!IsWindowVisible(h)) return true;
            var sb = new StringBuilder(256); GetWindowText(h, sb, 256);
            if (sb.ToString() != "Fighting Game") return true;
            uint pid; GetWindowThreadProcessId(h, out pid);
            foreach (var p in pids) if (pid == p) { found = h; return false; }
            return true; }, IntPtr.Zero);
        return found;
    }
}
"@
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$root = (Start-Process -FilePath $Exe -PassThru).Id
Write-Host "root pid $root"
$tree = @($root)
$hw = [IntPtr]::Zero
for ($i = 0; $i -lt 60 -and $hw -eq [IntPtr]::Zero; $i++) {
    Start-Sleep -Milliseconds 1000
    Get-CimInstance Win32_Process | Where-Object { $tree -contains $_.ParentProcessId -and $tree -notcontains $_.ProcessId } |
        ForEach-Object { $tree += $_.ProcessId }
    $hw = [K]::Find([uint32[]]$tree)
}
if ($hw -eq [IntPtr]::Zero) { Write-Host "no window"; $tree | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue }; exit 1 }
Write-Host "tree: $($tree -join ',')"
Write-Host "window $hw"
[K]::ShowWindow($hw, 9) | Out-Null
[K]::SetForegroundWindow($hw) | Out-Null
Start-Sleep -Seconds 3

function Snap([string]$name) {
    $r = New-Object K+R
    [K]::GetWindowRect($hw, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap($w, $h)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    [K]::PrintWindow($hw, $hdc, 2) | Out-Null
    $g.ReleaseHdc($hdc)
    $g.Dispose()
    $bmp.Save("$OutDir\$name.png", [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

Snap "00_idle"

[K]::KeyDown($hw, 0x44)                      # hold d
for ($i = 1; $i -le 6; $i++) { Start-Sleep -Milliseconds 450; Snap ("10_right_{0}" -f $i) }
[K]::KeyUp($hw, 0x44)
Start-Sleep -Milliseconds 700
Snap "11_after_right"

[K]::KeyDown($hw, 0x41)                      # hold a
for ($i = 1; $i -le 5; $i++) { Start-Sleep -Milliseconds 450; Snap ("20_left_{0}" -f $i) }
[K]::KeyUp($hw, 0x41)
Start-Sleep -Milliseconds 700
Snap "21_after_left"

[K]::KeyDown($hw, 0x57)                      # hold w
for ($i = 1; $i -le 4; $i++) { Start-Sleep -Milliseconds 400; Snap ("30_up_{0}" -f $i) }
[K]::KeyUp($hw, 0x57)
Start-Sleep -Milliseconds 700
Snap "31_after_up"

$childPid = ($tree | Where-Object { $_ -ne $root } | Select-Object -First 1)
$c1 = (Get-Process -Id $childPid -EA SilentlyContinue).CPU
Start-Sleep -Seconds 2
$c2 = (Get-Process -Id $childPid -EA SilentlyContinue).CPU
Write-Host ("child pid {0} cpu delta over 2s: {1:N2}s" -f $childPid, ($c2 - $c1))

$tree | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue }
Write-Host "done"
Get-ChildItem $OutDir | Select-Object Name, Length | Format-Table -AutoSize
