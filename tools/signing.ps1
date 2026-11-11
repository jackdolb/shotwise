<#
.SYNOPSIS
  Auxiliar de assinatura de codigo do Shotwise.
.EXAMPLES
  # 1) cria um certificado DE TESTE (autoassinado) e exporta .pfx e .cer
  .\tools\signing.ps1 -NewTestCert -Subject "CN=Shotwise Teste" -OutDir .\cert
  # 2) confere a assinatura de um arquivo
  .\tools\signing.ps1 -Verify .\dist_installer\Shotwise-Setup-1.11.0.exe
  # 3) mostra o hash do certificado de um arquivo assinado (para a regra do App Control)
  .\tools\signing.ps1 -Info .\dist_installer\Shotwise-Setup-1.11.0.exe
#>
[CmdletBinding(DefaultParameterSetName = "Verify")]
param(
    [Parameter(ParameterSetName = "New", Mandatory)] [switch]$NewTestCert,
    [Parameter(ParameterSetName = "New")] [string]$Subject = "CN=Shotwise Teste",
    [Parameter(ParameterSetName = "New")] [string]$OutDir = ".\cert",
    [Parameter(ParameterSetName = "New")] [int]$Years = 2,
    [Parameter(ParameterSetName = "Verify", Mandatory)] [string]$Verify,
    [Parameter(ParameterSetName = "Info", Mandatory)] [string]$Info
)

if ($NewTestCert) {
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject -KeyAlgorithm RSA -KeyLength 3072 `
        -HashAlgorithm SHA256 -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears($Years)
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $pwd1 = Read-Host "Senha para o .pfx" -AsSecureString
    $pfx = Join-Path $OutDir "shotwise-test.pfx"
    $cer = Join-Path $OutDir "shotwise-test.cer"
    Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $pwd1 | Out-Null
    Export-Certificate -Cert $cert -FilePath $cer | Out-Null
    Write-Host "Certificado criado. Impressao digital (SHA1): $($cert.Thumbprint)"
    Write-Host "  .pfx (chave privada - NAO versionar): $pfx"
    Write-Host "  .cer (publico, para confiar nas maquinas de teste): $cer"
    Write-Host "Para o build:"
    Write-Host "  set SHOTWISE_SIGN_PFX=$((Resolve-Path $pfx).Path)"
    Write-Host "  set SHOTWISE_SIGN_PASSWORD=<a senha>"
    return
}

$path = if ($Verify) { $Verify } else { $Info }
if (-not (Test-Path -LiteralPath $path)) {
    Write-Host "Arquivo nao encontrado: $path  (gere-o primeiro com build_installer.bat)"
    exit 1
}
$sig = Get-AuthenticodeSignature -FilePath $path
if ($Verify) {
    "{0}: {1}" -f $path, $sig.Status
    if ($sig.SignerCertificate) { "Assinante: " + $sig.SignerCertificate.Subject }
    if ($sig.TimeStamperCertificate) { "Carimbo de tempo: " + $sig.TimeStamperCertificate.Subject } else { "ATENCAO: sem carimbo de tempo." }
    if ($sig.Status -ne "Valid") { exit 1 }
} else {
    if (-not $sig.SignerCertificate) { "Arquivo sem assinatura."; exit 1 }
    $c = $sig.SignerCertificate
    "Assinante:       $($c.Subject)"
    "Emissor:         $($c.Issuer)"
    "Validade:        $($c.NotBefore.ToString("yyyy-MM-dd")) a $($c.NotAfter.ToString("yyyy-MM-dd"))"
    "Thumbprint SHA1: $($c.Thumbprint)"
    $chain = New-Object Security.Cryptography.X509Certificates.X509Chain
    [void]$chain.Build($c)
    "Cadeia:"
    $chain.ChainElements | ForEach-Object { "  - " + $_.Certificate.Subject }
}
