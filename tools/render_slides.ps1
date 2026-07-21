param(
    [Parameter(Mandatory = $true)]
    [string] $Source,
    [string] $OutputDirectory = "generated\renders",
    [int] $Width = 1440,
    [int] $Height = 1080
)

$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$outputPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

$powerPoint = $null
$presentation = $null
try {
    $powerPoint = New-Object -ComObject PowerPoint.Application
    $powerPoint.Visible = $false
    # Open read-only and without a window; exporting does not modify the source.
    $presentation = $powerPoint.Presentations.Open($sourcePath, $true, $false, $false)
    $base = Join-Path $outputPath "slide"
    $presentation.Export($base, "PNG", $Width, $Height)
    Write-Output ("Rendered {0} slides to {1}" -f $presentation.Slides.Count, $outputPath)
}
finally {
    if ($presentation -ne $null) {
        $presentation.Close()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
    }
    if ($powerPoint -ne $null) {
        $powerPoint.Quit()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
