param([switch]$Refresh)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Security
$directory=Join-Path $env:LOCALAPPDATA 'Memorybenchmark'
$target=Join-Path $directory 'gateway-task.dpapi'
if((Test-Path -LiteralPath $target) -and -not $Refresh){@{configured=$true;changed=$false}|ConvertTo-Json -Compress;exit 0}
$pointer=[IntPtr]::Zero;$plain=$null
try{
 $secure=ConvertTo-SecureString ((Get-Content -LiteralPath (Join-Path $directory 'gateway.dpapi') -Raw).Trim())
 $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
 $plain=[Text.Encoding]::UTF8.GetBytes([Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer))
 $cipher=[Security.Cryptography.ProtectedData]::Protect($plain,$null,[Security.Cryptography.DataProtectionScope]::LocalMachine)
 [IO.File]::WriteAllBytes($target,$cipher)
 $acl=New-Object Security.AccessControl.FileSecurity
 $acl.SetAccessRuleProtection($true,$false)
 foreach($identity in @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value,'S-1-5-18','S-1-5-32-544')){
  $sid=New-Object Security.Principal.SecurityIdentifier($identity)
  $rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','Allow')
  $acl.AddAccessRule($rule)
 }
 Set-Acl -LiteralPath $target -AclObject $acl
 @{configured=$true;changed=$true;scope='machine DPAPI with owner/SYSTEM/Administrators ACL';plaintext_written=$false}|ConvertTo-Json -Compress
}finally{
 if($plain){[Array]::Clear($plain,0,$plain.Length)}
 if($pointer -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)}
}
