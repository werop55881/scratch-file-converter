param(
  [string]$ProcName,
  [int]$ProcId = 0,
  [Parameter(Mandatory = $true)][string]$OutPng,
  [int]$WaitMs = 15000,
  [int]$SettleMs = 1500
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Shot {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, int flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$deadline = [DateTime]::UtcNow.AddMilliseconds($WaitMs)
$proc = $null
while ([DateTime]::UtcNow -lt $deadline) {
  if ($ProcId -gt 0) {
    $proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if ($proc -and $proc.MainWindowHandle -eq 0) { $proc = $null }
  } else {
    $proc = Get-Process -Name $ProcName -ErrorAction SilentlyContinue |
      Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
  }
  if ($proc) { break }
  Start-Sleep -Milliseconds 250
}
if (-not $proc) { Write-Output "NO WINDOW for $ProcName$ProcId"; exit 1 }
Start-Sleep -Milliseconds $SettleMs
$proc.Refresh()
$hwnd = $proc.MainWindowHandle
$rect = New-Object Win32Shot+RECT
[Win32Shot]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top
if ($w -le 0 -or $h -le 0) { Write-Output "BAD RECT $w x $h"; exit 1 }
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[Win32Shot]::PrintWindow($hwnd, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc)
$g.Dispose()
$bmp.Save($OutPng, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "SAVED $OutPng ${w}x${h}"
