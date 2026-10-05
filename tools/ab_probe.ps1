# v5: keys via PostMessage, capture via CopyFromScreen with TOPMOST raise.
# -Mode py|exe   py = run build\dev-fg\main.py, exe = frozen build
param([ValidateSet('py','exe')][string]$Mode = 'py')
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class V5 {
    public delegate bool Proc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(Proc cb, IntPtr l);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out R r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref Pt p);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint mapType);
    [StructLayout(LayoutKind.Sequential)] public struct R { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] public struct Pt { public int X, Y; }
    public static readonly IntPtr TOPMOST = (IntPtr)(-1);
    public static readonly IntPtr NOTOPMOST = (IntPtr)(-2);
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
    public static void Key(IntPtr h, bool down, byte vk) {
        uint sc = MapVirtualKey(vk, 0);
        IntPtr lp = (IntPtr)(int)((down ? 0x00000001u : 0xC0000001u) | (sc << 16));
        PostMessage(h, down ? 0x100u : 0x101u, (IntPtr)vk, lp);
    }
}
"@
$out = "$env:TEMP\opencode\ab_$Mode"
Remove-Item "$out\*.png" -EA SilentlyContinue
New-Item -ItemType Directory -Force -Path $out | Out-Null

if ($Mode -eq 'py') {
    Start-Process -FilePath python -ArgumentList 'main.py' -WorkingDirectory 'C:\Users\werop\ScratchFileConverter\build\dev-fg' -PassThru | Out-Null
} else {
    Start-Process -FilePath "$env:USERPROFILE\Downloads\Saves\Fighting Game-python\Fighting Game.exe" -PassThru | Out-Null
}
Start-Sleep -Milliseconds 500
$root = (Get-Process | Where-Object { $_.ProcessName -match '^(python|Fighting Game)$' -and $_.StartTime -gt (Get-Date).AddSeconds(-10) } | Sort-Object StartTime | Select-Object -Last 1).Id
Write-Host "root $root"
$tree = @($root)
$hw = [IntPtr]::Zero
for ($i = 0; $i -lt 45 -and $hw -eq [IntPtr]::Zero; $i++) {
    Start-Sleep -Milliseconds 1000
    Get-CimInstance Win32_Process | Where-Object { $tree -contains $_.ParentProcessId -and $tree -notcontains $_.ProcessId } |
        ForEach-Object { $tree += $_.ProcessId }
    $hw = [V5]::Find([uint32[]]$tree)
}
if ($hw -eq [IntPtr]::Zero) { Write-Host "no window"; $tree | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue }; exit 1 }
Write-Host "window $hw tree $($tree -join ',')"
[V5]::ShowWindow($hw, 9) | Out-Null
[V5]::SetWindowPos($hw, [V5]::TOPMOST, 0, 0, 0, 0, 0x0001 -bor 0x0002) | Out-Null   # raise above all
Start-Sleep -Seconds 3

function Snap([string]$name) {
    $cr = New-Object V5+R
    [V5]::GetClientRect($hw, [ref]$cr) | Out-Null
    $pt = New-Object V5+Pt
    [V5]::ClientToScreen($hw, [ref]$pt) | Out-Null
    $w = $cr.Right - $cr.Left; $h = $cr.Bottom - $cr.Top
    $bmp = New-Object System.Drawing.Bitmap($w, $h)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($pt.X, $pt.Y, 0, 0, $bmp.Size)
    $g.Dispose()
    $bmp.Save("$out\$name.png", [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

Snap "00_idle"
[V5]::Key($hw, $true, 0x44)
for ($i = 1; $i -le 6; $i++) { Start-Sleep -Milliseconds 450; Snap ("10_right_$i") }
[V5]::Key($hw, $false, 0x44)
Start-Sleep -Milliseconds 700
Snap "11_after_right"
[V5]::Key($hw, $true, 0x57)
for ($i = 1; $i -le 4; $i++) { Start-Sleep -Milliseconds 400; Snap ("30_up_$i") }
[V5]::Key($hw, $false, 0x57)
Start-Sleep -Milliseconds 700
Snap "31_after_up"

$childPid = ($tree | Where-Object { $_ -ne $root } | Select-Object -First 1)
$c1 = (Get-Process -Id $childPid -EA SilentlyContinue).CPU
Start-Sleep -Seconds 2
$c2 = (Get-Process -Id $childPid -EA SilentlyContinue).CPU
Write-Host ("child $childPid cpu 2s: {0:N2}s" -f ($c2 - $c1))
[V5]::SetWindowPos($hw, [V5]::NOTOPMOST, 0, 0, 0, 0, 0x0001 -bor 0x0002) | Out-Null
$tree | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue }
Write-Host "hashes:"
(Get-ChildItem "$out\*.png" | Get-FileHash -Algorithm MD5).Hash | Group-Object | Select-Object Count | Format-Table
