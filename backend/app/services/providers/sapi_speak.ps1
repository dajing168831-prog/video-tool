# Windows SAPI text-to-speech -> wav.
# Dev-machine only; production uses the Volcengine TTS provider.
# ASCII-only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI unless it
# has a BOM, and non-ASCII comments break parsing.
param(
    [Parameter(Mandatory=$true)][string]$TextFile,
    [Parameter(Mandatory=$true)][string]$OutFile,
    [string]$Voice = "",
    [int]$Rate = 0
)

Add-Type -AssemblyName System.Speech
$text = Get-Content -LiteralPath $TextFile -Raw -Encoding UTF8
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

if ($Voice -ne "") {
    try { $synth.SelectVoice($Voice) } catch { }
}

# Fall back to the first installed Chinese voice.
$current = $synth.Voice.VoiceInfo.Culture.Name
if ($current -notlike "zh*") {
    $zh = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like "zh*" } | Select-Object -First 1
    if ($zh) { $synth.SelectVoice($zh.VoiceInfo.Name) }
}

$synth.Rate = $Rate
$synth.SetOutputToWaveFile($OutFile)
$synth.Speak($text)
$synth.Dispose()
Write-Output "OK"
