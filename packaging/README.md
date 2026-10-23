# Package manager manifests

Ready-to-publish manifests for the GUI `.exe` attached to every GitHub
release. Nothing here is automated yet - follow the steps below to publish.

## Scoop (Windows)

Scoop needs a bucket repo (this repo is not bucket-shaped). To publish:

1. Create an empty repo, e.g. `sb3conv-scoop`.
2. Copy `scoop/sb3conv.json` into its root.
3. Users install with:

   ```powershell
   scoop bucket add sb3conv https://github.com/werop55881/sb3conv-scoop
   scoop install sb3conv
   ```

`checkver: github` + `autoupdate` mean a plain `scoop update` follows new
releases once the json's version and hash are bumped per release.

## winget (Windows)

`winget/` mirrors the file layout
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) expects
for `werop55881.ScratchFileConverter`:

```
manifests/w/werop55881/ScratchFileConverter/<version>/
  werop55881.ScratchFileConverter.yaml
  werop55881.ScratchFileConverter.installer.yaml
  werop55881.ScratchFileConverter.locale.en-US.yaml
```

To publish a new version:

1. Bump `PackageVersion` in all three files and refresh `InstallerSha256`
   (PowerShell: `(Get-FileHash sb3conv-gui.exe).Hash` - winget wants
   uppercase, scoop lowercase).
2. Open a PR against `microsoft/winget-pkgs` with the three files in the
   version directory above, or let the tooling do it:

   ```powershell
   wingetcreate update werop55881.ScratchFileConverter `
     --version 0.5.0 `
     --urls https://github.com/werop55881/scratch-file-converter/releases/download/v0.5.0/sb3conv-gui.exe `
     --submit
   ```

Users then get `winget install werop55881.ScratchFileConverter` (once the
manifest is merged upstream).
