$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voice = $synth.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh*' } | Select-Object -First 1
    if (-not $voice) { throw 'No installed Chinese voice' }
    $synth.SelectVoice($voice.VoiceInfo.Name)
    $synth.Rate = 1
    $synth.SetOutputToWaveFile([string]$request.output)
    $synth.Speak([string]$request.text)
} finally { $synth.Dispose() }
