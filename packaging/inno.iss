; novel-down 安装版（EXE 安装器）脚本 —— 供 Inno Setup 6 使用。
;
; ⚠ 本机构建状态：**Inno Setup 未安装，且外网下载被拦**（实测只回 315 字节错误页），
;   所以本脚本**尚未实际编译过**。在有 ISCC.exe 的机器上执行：
;
;     ISCC.exe packaging\inno.iss
;
; 产物：dist\novel-down-0.8.37-setup.exe
;
; 前置：先跑 `python packaging/build.py --portable` 生成 dist\noveldown\（onedir 版）。
; 本安装器做的事：把 onedir 目录装到 {pf}\novel-down、加开始菜单快捷方式、
; 写卸载项、可选把安装目录加进 PATH。

#define MyAppName "novel-down"
#define MyAppVersion "0.8.37"
#define MyAppPublisher "siwpan"
#define MyAppURL "https://gitee.com/siwpan/novel-down"
#define MyAppExeName "noveldown.exe"
; onedir 便携版的目录（由 PyInstaller 生成）
#define PortableDir "dist\noveldown"

[Setup]
AppId={{8F1B2C3D-4E5A-6B7C-8D9E-0F1A2B3C4D5E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\novel-down
DefaultGroupName={#MyAppName}
; 本项目是**控制台程序**，没有 GUI，所以开始菜单里放的是「命令行」快捷方式
OutputDir=dist
OutputBaseFilename=novel-down-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; 需要管理员权限才能写 {pf}
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
InfoBeforeFile=..\README.md
UninstallDisplayName={#MyAppName} {#MyAppVersion}
; ⚠ 与 MSI 用**同一个** UpgradeCode，保证两种安装形态不会互相冲突
AppMutex=novel-down-installer

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"
Name: "addtopath"; Description: "把安装目录加入 PATH（可在任意命令行直接用 noveldown）"; GroupDescription: "其他任务:"

[Files]
; onedir 的全部内容（exe + _internal + 规则数据）
Source: "{#PortableDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\novel-down 命令行"; Filename: "cmd.exe"; Parameters: "/k ""{app}\{#MyAppExeName}"" --help"; WorkingDir: "{app}"
Name: "{group}\卸载 novel-down"; Filename: "{uninstallexe}"
Name: "{autodesktop}\novel-down"; Filename: "cmd.exe"; Parameters: "/k ""{app}\{#MyAppExeName}"" --help"; Tasks: desktopicon

[Registry]
; 把安装目录追加到用户 PATH（卸载时还原）
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; Check: NeedsAddPath('{app}'); Tasks: addtopath

[Code]
{ 判断 PATH 里是否已有该目录，避免重复追加 }
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;
