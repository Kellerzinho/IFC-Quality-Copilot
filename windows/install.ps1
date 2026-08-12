[CmdletBinding()]
param(
    [string]$PackageRoot = $PSScriptRoot,
    [string]$AppRoot = (Join-Path $env:LOCALAPPDATA 'IFCQualityCopilot'),
    [switch]$ValidateOnly,
    [switch]$PlanOnly,
    [string]$TestProbeJson = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ExpectedToolPins = [ordered]@{
    uv = [ordered]@{
        version = '0.12.3'
        url = 'https://github.com/astral-sh/uv/releases/download/0.12.3/uv-x86_64-pc-windows-msvc.zip'
        sha256 = 'b23350c79e8ad0192b8124af13a0f17e8d4e4549524785e1aef389ae5a06990e'
        size_bytes = [int64]19013455
    }
    ollama = [ordered]@{
        version = '0.32.5'
        url = 'https://github.com/ollama/ollama/releases/download/v0.32.5/ollama-windows-amd64.zip'
        sha256 = '7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb'
        size_bytes = [int64]1457824795
    }
    ollama_rocm = [ordered]@{
        version = '0.32.5'
        url = 'https://github.com/ollama/ollama/releases/download/v0.32.5/ollama-windows-amd64-rocm.zip'
        sha256 = 'f2284e7008ffd64eadb7a05ac4ca1a0de843d1e8d0c861aa0923ef855ca94615'
        size_bytes = [int64]245370090
    }
    llmfit = [ordered]@{
        version = '1.1.8'
        url = 'https://github.com/AlexsJones/llmfit/releases/download/v1.1.8/llmfit-v1.1.8-x86_64-pc-windows-msvc.zip'
        sha256 = 'bf8a509d68bc02f4cafc7040501938a30841eeb8c496eda51ae886a2f43a88e2'
        size_bytes = [int64]5249067
    }
}

function Assert-ExactKeys {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string[]]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($null -eq $Value) {
        throw "$Label ausente."
    }
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    if (($actual -join "`n") -cne ($wanted -join "`n")) {
        throw "$Label possui campos inesperados ou ausentes."
    }
}

function Assert-Integer {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Label,
        [int64]$Minimum = 0
    )

    if (($Value -isnot [int]) -and ($Value -isnot [long])) {
        throw "$Label deve ser inteiro."
    }
    if ([int64]$Value -lt $Minimum) {
        throw "$Label abaixo do minimo."
    }
}

function Assert-LowerSha256 {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (($Value -isnot [string]) -or ($Value -cnotmatch '^[0-9a-f]{64}$')) {
        throw "$Label deve ser SHA-256 hexadecimal em minusculas."
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-ManifestRecordShape {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [Parameter(Mandatory = $true)][string]$Label
    )

    Assert-ExactKeys -Value $Record -Expected @('path', 'size_bytes', 'sha256') -Label $Label
    if (($Record.path -isnot [string]) -or ([string]$Record.path -cne $ExpectedPath)) {
        throw "Caminho fixado divergente em $Label."
    }
    Assert-Integer -Value $Record.size_bytes -Label "$Label.size_bytes" -Minimum 1
    Assert-LowerSha256 -Value $Record.sha256 -Label "$Label.sha256"
}

function Assert-InternalRecord {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$PromptRecord
    )

    $keys = @('project_path', 'size_bytes', 'sha256')
    if ($PromptRecord) {
        $keys += 'version'
    }
    Assert-ExactKeys -Value $Record -Expected $keys -Label $Label
    if (($Record.project_path -isnot [string]) -or
        ([string]$Record.project_path -cne $ExpectedPath)) {
        throw "Caminho interno fixado divergente em $Label."
    }
    Assert-Integer -Value $Record.size_bytes -Label "$Label.size_bytes" -Minimum 1
    Assert-LowerSha256 -Value $Record.sha256 -Label "$Label.sha256"
    if ($PromptRecord -and
        (($Record.version -isnot [string]) -or ([string]$Record.version -cne 'v7.6')) ) {
        throw 'Versao de prompt fixada divergente; esperado v7.6.'
    }
}

function Assert-Inputs {
    param(
        [Parameter(Mandatory = $true)]$Inputs,
        [Parameter(Mandatory = $true)]$Datasets
    )

    Assert-ExactKeys -Value $Inputs `
        -Expected @('models_lock', 'prompt_templates', 'datasets') `
        -Label 'inputs'
    Assert-InternalRecord -Record $Inputs.models_lock `
        -ExpectedPath 'src/experiment/results/models.lock.json' `
        -Label 'inputs.models_lock'
    Assert-InternalRecord -Record $Inputs.prompt_templates `
        -ExpectedPath 'src/suggestion_engine/prompt_templates.py' `
        -Label 'inputs.prompt_templates' -PromptRecord
    Assert-ExactKeys -Value $Inputs.datasets -Expected @('predio', 'casa') `
        -Label 'inputs.datasets'

    foreach ($dataset in @('predio', 'casa')) {
        $entry = $Inputs.datasets.PSObject.Properties[$dataset].Value
        Assert-ExactKeys -Value $entry -Expected @('ifc', 'ground_truth', 'ids') `
            -Label "inputs.datasets.$dataset"
        $ifcPath = "payload/datasets/${dataset}_v1.ifc"
        Assert-ManifestRecordShape -Record $entry.ifc -ExpectedPath $ifcPath `
            -Label "inputs.datasets.$dataset.ifc"
        $outer = $Datasets.PSObject.Properties[$dataset].Value
        if (([int64]$entry.ifc.size_bytes -ne [int64]$outer.size_bytes) -or
            ([string]$entry.ifc.sha256 -cne [string]$outer.sha256)) {
            throw "Registro IFC duplicado divergente para $dataset."
        }
        Assert-InternalRecord -Record $entry.ground_truth `
            -ExpectedPath "data/evaluation/$dataset/ground_truth.yaml" `
            -Label "inputs.datasets.$dataset.ground_truth"
        Assert-InternalRecord -Record $entry.ids `
            -ExpectedPath 'data/ids_templates/residencial_nbr15575.ids' `
            -Label "inputs.datasets.$dataset.ids"
    }

    $predioIds = $Inputs.datasets.predio.ids
    $casaIds = $Inputs.datasets.casa.ids
    if (([int64]$predioIds.size_bytes -ne [int64]$casaIds.size_bytes) -or
        ([string]$predioIds.sha256 -cne [string]$casaIds.sha256)) {
        throw 'Pins IDS divergentes entre os datasets.'
    }
}

function Assert-ToolPins {
    param([Parameter(Mandatory = $true)]$Tools)

    $toolNames = @('uv', 'ollama', 'ollama_rocm', 'llmfit')
    Assert-ExactKeys -Value $Tools -Expected $toolNames -Label 'tools'
    foreach ($name in $toolNames) {
        $actual = $Tools.PSObject.Properties[$name].Value
        $expected = $script:ExpectedToolPins[$name]
        Assert-ExactKeys -Value $actual `
            -Expected @('version', 'url', 'sha256', 'size_bytes') `
            -Label "tools.$name"
        foreach ($field in @('version', 'url', 'sha256')) {
            if (($actual.PSObject.Properties[$field].Value -isnot [string]) -or
                ([string]$actual.PSObject.Properties[$field].Value -cne
                    [string]$expected[$field])) {
                throw "Pin fixado divergente: tools.$name.$field"
            }
        }
        Assert-Integer -Value $actual.size_bytes -Label "tools.$name.size_bytes" -Minimum 1
        if ([int64]$actual.size_bytes -ne [int64]$expected.size_bytes) {
            throw "Pin fixado divergente: tools.$name.size_bytes"
        }
    }
}

function Read-ValidatedManifest {
    param([Parameter(Mandatory = $true)][string]$ManifestPath)

    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw 'release-manifest.json ausente.'
    }
    try {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
    }
    catch {
        throw 'release-manifest.json nao e JSON valido.'
    }

    Assert-ExactKeys -Value $manifest -Expected @(
        'schema_version', 'platform', 'minimum_windows_build', 'python_version',
        'tools', 'release_id', 'source_commit', 'project', 'datasets', 'inputs'
    ) -Label 'manifesto'
    if (($manifest.schema_version -isnot [int]) -or
        ([int]$manifest.schema_version -ne 1)) {
        throw 'schema_version fixado divergente; esperado 1.'
    }
    if (($manifest.platform -isnot [string]) -or
        ([string]$manifest.platform -cne 'windows-x86_64')) {
        throw 'platform fixado divergente; esperado windows-x86_64.'
    }
    if (($manifest.minimum_windows_build -isnot [int]) -or
        ([int]$manifest.minimum_windows_build -ne 19045)) {
        throw 'minimum_windows_build fixado divergente; esperado 19045.'
    }
    if (($manifest.python_version -isnot [string]) -or
        ([string]$manifest.python_version -cne '3.12.13')) {
        throw 'python_version fixado divergente; esperado 3.12.13.'
    }
    if (($manifest.release_id -isnot [string]) -or
        ([string]$manifest.release_id -cnotmatch '^ifcqc-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{12}$')) {
        throw 'release_id invalido.'
    }
    if (($manifest.source_commit -isnot [string]) -or
        ([string]$manifest.source_commit -cnotmatch
            '^(?:[0-9a-f]{40,64}|tree-[0-9a-f]{64})$')) {
        throw 'source_commit invalido.'
    }

    Assert-ToolPins -Tools $manifest.tools
    Assert-ManifestRecordShape -Record $manifest.project `
        -ExpectedPath 'payload/project.zip' -Label 'project'
    Assert-ExactKeys -Value $manifest.datasets -Expected @('predio', 'casa') `
        -Label 'datasets'
    Assert-ManifestRecordShape -Record $manifest.datasets.predio `
        -ExpectedPath 'payload/datasets/predio_v1.ifc' -Label 'datasets.predio'
    Assert-ManifestRecordShape -Record $manifest.datasets.casa `
        -ExpectedPath 'payload/datasets/casa_v1.ifc' -Label 'datasets.casa'
    Assert-Inputs -Inputs $manifest.inputs -Datasets $manifest.datasets
    return $manifest
}

function Assert-PayloadRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)]$Record
    )

    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([char[]]@('\', '/'))
    $relative = [string]$Record.path
    if ([IO.Path]::IsPathRooted($relative) -or $relative.Contains('\') -or
        $relative.Contains(':') -or ($relative.Split('/') -contains '..')) {
        throw "Caminho de payload invalido: $relative"
    }
    $target = [IO.Path]::GetFullPath((Join-Path $rootFull $relative))
    $boundary = $rootFull + [IO.Path]::DirectorySeparatorChar
    if (-not $target.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Caminho fora do pacote: $relative"
    }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "Arquivo de payload ausente: $relative"
    }
    if ((Get-Sha256 -LiteralPath $target) -cne [string]$Record.sha256) {
        throw "SHA-256 divergente: $relative"
    }
    if ((Get-Item -LiteralPath $target).Length -ne [int64]$Record.size_bytes) {
        throw "Tamanho divergente: $relative"
    }
}

function Assert-ExactPayloadFiles {
    param([Parameter(Mandatory = $true)][string]$Root)

    $payloadRoot = Join-Path $Root 'payload'
    if (-not (Test-Path -LiteralPath $payloadRoot -PathType Container)) {
        throw 'Pasta payload ausente.'
    }
    $actual = @(
        Get-ChildItem -LiteralPath $payloadRoot -Recurse -Force |
            Where-Object { -not $_.PSIsContainer } |
            ForEach-Object {
                $_.FullName.Substring($Root.Length).TrimStart([char[]]@('\', '/')).Replace('\', '/')
            } |
            Sort-Object
    )
    $expected = @(
        'payload/datasets/casa_v1.ifc',
        'payload/datasets/predio_v1.ifc',
        'payload/project.zip'
    ) | Sort-Object
    if (($actual -join "`n") -cne ($expected -join "`n")) {
        throw 'Conteudo do payload deve conter exatamente project.zip, predio_v1.ifc e casa_v1.ifc.'
    }
}

function Get-PlatformProbe {
    param([string]$ProbeJson)

    if ($ProbeJson) {
        if ($env:IFCQC_TESTING -cne '1') {
            throw 'TestProbeJson so pode ser usado em testes controlados.'
        }
        if (-not (Test-Path -LiteralPath $ProbeJson -PathType Leaf)) {
            throw 'Arquivo TestProbeJson ausente.'
        }
        $probe = Get-Content -LiteralPath $ProbeJson -Raw -Encoding UTF8 |
            ConvertFrom-Json
        Assert-ExactKeys -Value $probe `
            -Expected @('windows_build', 'os_architecture', 'process_architecture') `
            -Label 'probe de plataforma'
        return $probe
    }

    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    return [pscustomobject]@{
        windows_build = [int]$os.BuildNumber
        os_architecture = [string]$os.OSArchitecture
        process_architecture = [string]$env:PROCESSOR_ARCHITECTURE
    }
}

function Get-ExistingDirectoryAncestor {
    param([Parameter(Mandatory = $true)][string]$Path)

    $candidate = [IO.Path]::GetFullPath($Path)
    while (-not (Test-Path -LiteralPath $candidate)) {
        $parent = [IO.Directory]::GetParent($candidate)
        if ($null -eq $parent) {
            throw "Nao foi possivel localizar ancestral gravavel para AppRoot."
        }
        $candidate = $parent.FullName
    }
    if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
        throw 'AppRoot deve ser um diretorio, nao um arquivo.'
    }
    return $candidate
}

function Test-WriteProbe {
    param(
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ((Test-Path -LiteralPath $TargetPath) -and
        -not (Test-Path -LiteralPath $TargetPath -PathType Container)) {
        throw "$Label deve ser um diretorio, nao um arquivo."
    }
    $ancestor = Get-ExistingDirectoryAncestor -Path $TargetPath
    $probeDirectory = Join-Path $ancestor ('.ifcqc-write-probe-' + [guid]::NewGuid().ToString('N'))
    $probeFile = Join-Path $probeDirectory 'probe.txt'
    $directoryCreated = $false
    try {
        [IO.Directory]::CreateDirectory($probeDirectory) | Out-Null
        $directoryCreated = $true
        [IO.File]::WriteAllText($probeFile, 'ok')
    }
    catch {
        throw "$Label nao permite escrita: $($_.Exception.Message)"
    }
    finally {
        if (Test-Path -LiteralPath $probeFile -PathType Leaf) {
            Remove-Item -LiteralPath $probeFile -Force -ErrorAction SilentlyContinue
        }
        if ($directoryCreated -and (Test-Path -LiteralPath $probeDirectory -PathType Container)) {
            Remove-Item -LiteralPath $probeDirectory -Force -ErrorAction SilentlyContinue
        }
    }
    return $ancestor
}

function Get-AvailableBytes {
    param([Parameter(Mandatory = $true)][string]$ExistingPath)

    $root = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($ExistingPath))
    if (-not $root) {
        throw 'Nao foi possivel determinar o volume do AppRoot.'
    }
    $drive = New-Object -TypeName System.IO.DriveInfo -ArgumentList $root
    return [int64]$drive.AvailableFreeSpace
}

function Test-OfflinePreflight {
    param(
        [Parameter(Mandatory = $true)][string]$PackagePath,
        [Parameter(Mandatory = $true)][string]$InstallPath,
        [Parameter(Mandatory = $true)][string]$LaunchPath,
        [string]$ProbeJson = ''
    )

    $packageFull = [IO.Path]::GetFullPath($PackagePath).TrimEnd([char[]]@('\', '/'))
    $installFull = [IO.Path]::GetFullPath($InstallPath).TrimEnd([char[]]@('\', '/'))
    $launchFull = [IO.Path]::GetFullPath($LaunchPath).TrimEnd([char[]]@('\', '/'))
    if (-not (Test-Path -LiteralPath $packageFull -PathType Container)) {
        throw 'PackageRoot ausente ou nao e diretorio.'
    }

    # Ordem intencional: plataforma, manifesto/payload, escrita e disco, depois rede.
    $probe = Get-PlatformProbe -ProbeJson $ProbeJson
    Assert-Integer -Value $probe.windows_build -Label 'windows_build' -Minimum 1
    if ([int]$probe.windows_build -lt 19045) {
        throw 'Windows build incompativel: minimo 19045 (Windows 10 22H2).'
    }
    if (([string]$probe.os_architecture -notmatch '64') -or
        ([string]$probe.process_architecture).ToUpperInvariant() -cne 'AMD64') {
        throw 'Plataforma incompativel: Windows x64 e processo AMD64 sao obrigatorios.'
    }

    $manifestPath = Join-Path $packageFull 'release-manifest.json'
    $manifest = Read-ValidatedManifest -ManifestPath $manifestPath
    Assert-ExactPayloadFiles -Root $packageFull
    Assert-PayloadRecord -Root $packageFull -Record $manifest.project
    Assert-PayloadRecord -Root $packageFull -Record $manifest.datasets.predio
    Assert-PayloadRecord -Root $packageFull -Record $manifest.datasets.casa

    $existingInstallAncestor = Test-WriteProbe -TargetPath $installFull -Label 'AppRoot'
    $launchWritable = $true
    try {
        $null = Test-WriteProbe -TargetPath $launchFull -Label 'launch_dir'
    }
    catch {
        $launchWritable = $false
    }
    $available = Get-AvailableBytes -ExistingPath $existingInstallAncestor
    $required = [int64](2GB + [int64]$manifest.tools.uv.size_bytes +
        (2 * [int64]$manifest.project.size_bytes))
    if ($available -lt $required) {
        throw "Espaco livre insuficiente para o bootstrap: necessario $required bytes."
    }

    return [pscustomobject]@{
        release_id = [string]$manifest.release_id
        python_version = [string]$manifest.python_version
        package_root = $packageFull
        install_root = $installFull
        project_root = Join-Path $installFull ('releases\' + [string]$manifest.release_id)
        launch_dir = $launchFull
        launch_dir_writable = $launchWritable
        available_bytes = $available
        required_bootstrap_bytes = $required
        manifest = $manifest
    }
}

function Assert-DownloadedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][int64]$ExpectedSize
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw 'Download ausente depois da transferencia.'
    }
    if ((Get-Sha256 -LiteralPath $Path) -cne $ExpectedSha256) {
        throw 'SHA-256 divergente no download do uv.'
    }
    if ((Get-Item -LiteralPath $Path).Length -ne $ExpectedSize) {
        throw 'Tamanho divergente no download do uv.'
    }
}

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Sha256,
        [Parameter(Mandatory = $true)][int64]$SizeBytes,
        [Parameter(Mandatory = $true)][string]$DownloadRoot
    )

    if ($env:IFCQC_TESTING -ceq '1') {
        if ($env:IFCQC_NETWORK_SENTINEL) {
            $sentinel = [IO.Path]::GetFullPath([string]$env:IFCQC_NETWORK_SENTINEL)
            $sentinelParent = Split-Path -Parent $sentinel
            if ($sentinelParent -and -not (Test-Path -LiteralPath $sentinelParent)) {
                New-Item -ItemType Directory -Path $sentinelParent | Out-Null
            }
            [IO.File]::WriteAllText($sentinel, 'network-entered')
        }
        if ($env:IFCQC_TEST_FAIL_STAGE -ceq 'uv_download') {
            throw (New-Object Net.WebException('Falha de download simulada.'))
        }
    }

    New-Item -ItemType Directory -Path $DownloadRoot -Force | Out-Null
    $destination = Join-Path $DownloadRoot $Sha256
    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        try {
            Assert-DownloadedFile -Path $destination -ExpectedSha256 $Sha256 `
                -ExpectedSize $SizeBytes
            return $destination
        }
        catch {
            $invalid = "$destination.invalid-$([guid]::NewGuid().ToString('N'))"
            Move-Item -LiteralPath $destination -Destination $invalid
        }
    }

    $partial = "$destination.partial"
    $previousSecurityProtocol = [Net.ServicePointManager]::SecurityProtocol
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            if (Test-Path -LiteralPath $partial) {
                Remove-Item -LiteralPath $partial -Force
            }
            try {
                Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing
                Assert-DownloadedFile -Path $partial -ExpectedSha256 $Sha256 `
                    -ExpectedSize $SizeBytes
                Move-Item -LiteralPath $partial -Destination $destination
                return $destination
            }
            catch {
                if (Test-Path -LiteralPath $partial) {
                    Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
                }
                if ($attempt -eq 3) {
                    throw "Falha ao baixar uv apos 3 tentativas: $($_.Exception.Message)"
                }
                Start-Sleep -Seconds $attempt
            }
        }
    }
    finally {
        [Net.ServicePointManager]::SecurityProtocol = $previousSecurityProtocol
    }
    throw 'Falha inesperada ao obter uv.'
}

function Move-ToRecovery {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RecoveryRoot,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    New-Item -ItemType Directory -Path $RecoveryRoot -Force | Out-Null
    $destination = Join-Path $RecoveryRoot (
        "$Name-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))-$([guid]::NewGuid().ToString('N'))"
    )
    Move-Item -LiteralPath $Path -Destination $destination
}

function Install-VerifiedUv {
    param(
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)][string]$InstallRoot,
        [Parameter(Mandatory = $true)][string]$ExpectedArchiveSha256
    )

    $toolRoot = Join-Path $InstallRoot 'tools\uv\0.12.3'
    $markerPath = Join-Path $toolRoot '.ifcqc-uv.json'
    if ((Test-Path -LiteralPath $toolRoot -PathType Container) -and
        (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        try {
            $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 |
                ConvertFrom-Json
            $uvCandidate = Get-ChildItem -LiteralPath $toolRoot -Filter uv.exe -Recurse |
                Select-Object -First 1
            if (($null -ne $uvCandidate) -and
                ([string]$marker.archive_sha256 -ceq $ExpectedArchiveSha256) -and
                ([string]$marker.executable_sha256 -ceq
                    (Get-Sha256 -LiteralPath $uvCandidate.FullName))) {
                return $uvCandidate.FullName
            }
        }
        catch {
            # A instalacao incompleta sera preservada em recovery logo abaixo.
        }
    }

    $recoveryRoot = Join-Path $InstallRoot 'state\recovery'
    Move-ToRecovery -Path $toolRoot -RecoveryRoot $recoveryRoot -Name 'uv-incomplete'
    $tempRoot = Join-Path $InstallRoot 'temp'
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $token = [guid]::NewGuid().ToString('N')
    $stage = Join-Path $tempRoot "uv-$token"
    $zipPath = Join-Path $tempRoot "uv-$token.zip"
    Copy-Item -LiteralPath $ArchivePath -Destination $zipPath
    try {
        Expand-Archive -LiteralPath $zipPath -DestinationPath $stage
        $uvStage = Get-ChildItem -LiteralPath $stage -Filter uv.exe -Recurse |
            Select-Object -First 1
        if ($null -eq $uvStage) {
            throw 'uv.exe ausente no arquivo oficial verificado.'
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $toolRoot) -Force |
            Out-Null
        Move-Item -LiteralPath $stage -Destination $toolRoot
        $uvInstalled = Get-ChildItem -LiteralPath $toolRoot -Filter uv.exe -Recurse |
            Select-Object -First 1
        $marker = [ordered]@{
            archive_sha256 = $ExpectedArchiveSha256
            executable_sha256 = Get-Sha256 -LiteralPath $uvInstalled.FullName
        } | ConvertTo-Json -Compress
        [IO.File]::WriteAllText($markerPath, $marker)
        return $uvInstalled.FullName
    }
    finally {
        if (Test-Path -LiteralPath $zipPath -PathType Leaf) {
            Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Assert-ProjectRecord {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $relative = [string]$Record.project_path
    if ([IO.Path]::IsPathRooted($relative) -or $relative.Contains('\') -or
        $relative.Contains(':') -or ($relative.Split('/') -contains '..')) {
        throw "Caminho interno invalido: $Label"
    }
    $path = Join-Path $ProjectRoot $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Entrada interna ausente: $Label"
    }
    if ((Get-Sha256 -LiteralPath $path) -cne [string]$Record.sha256) {
        throw "SHA-256 interno divergente: $Label"
    }
    if ((Get-Item -LiteralPath $path).Length -ne [int64]$Record.size_bytes) {
        throw "Tamanho interno divergente: $Label"
    }
}

function Assert-InstalledInputs {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)]$Manifest
    )

    Assert-ProjectRecord -ProjectRoot $ProjectRoot `
        -Record $Manifest.inputs.models_lock -Label 'models_lock'
    Assert-ProjectRecord -ProjectRoot $ProjectRoot `
        -Record $Manifest.inputs.prompt_templates -Label 'prompt_templates'
    foreach ($dataset in @('predio', 'casa')) {
        $entry = $Manifest.inputs.datasets.PSObject.Properties[$dataset].Value
        Assert-ProjectRecord -ProjectRoot $ProjectRoot -Record $entry.ground_truth `
            -Label "$dataset ground_truth"
        Assert-ProjectRecord -ProjectRoot $ProjectRoot -Record $entry.ids `
            -Label "$dataset ids"
    }
}

function Copy-VerifiedDatasets {
    param(
        [Parameter(Mandatory = $true)][string]$PackagePath,
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)]$Manifest
    )

    foreach ($dataset in @('predio', 'casa')) {
        $record = $Manifest.datasets.PSObject.Properties[$dataset].Value
        $source = Join-Path $PackagePath ([string]$record.path)
        $destinationDirectory = Join-Path $ProjectRoot "data\evaluation\$dataset"
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        $destination = Join-Path $destinationDirectory "${dataset}_v1.ifc"
        Copy-Item -LiteralPath $source -Destination $destination -Force
        if ((Get-Sha256 -LiteralPath $destination) -cne [string]$record.sha256) {
            throw "SHA-256 divergente ao copiar IFC $dataset."
        }
        if ((Get-Item -LiteralPath $destination).Length -ne [int64]$record.size_bytes) {
            throw "Tamanho divergente ao copiar IFC $dataset."
        }
    }
}

function Prepare-Project {
    param(
        [Parameter(Mandatory = $true)][string]$PackagePath,
        [Parameter(Mandatory = $true)][string]$InstallRoot,
        [Parameter(Mandatory = $true)]$Manifest
    )

    $projectRoot = Join-Path $InstallRoot ('releases\' + [string]$Manifest.release_id)
    $markerPath = Join-Path $projectRoot '.ifcqc-release.json'
    $canReuse = $false
    if ((Test-Path -LiteralPath $projectRoot -PathType Container) -and
        (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        try {
            $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 |
                ConvertFrom-Json
            if ([string]$marker.project_sha256 -ceq [string]$Manifest.project.sha256) {
                Assert-InstalledInputs -ProjectRoot $projectRoot -Manifest $Manifest
                $canReuse = $true
            }
        }
        catch {
            $canReuse = $false
        }
    }

    if (-not $canReuse) {
        $recovery = Join-Path $InstallRoot 'state\recovery'
        Move-ToRecovery -Path $projectRoot -RecoveryRoot $recovery `
            -Name ([string]$Manifest.release_id + '-incomplete')
        $tempRoot = Join-Path $InstallRoot 'temp'
        New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
        $stage = Join-Path $tempRoot ('project-' + [guid]::NewGuid().ToString('N'))
        $projectArchive = Join-Path $PackagePath ([string]$Manifest.project.path)
        Expand-Archive -LiteralPath $projectArchive -DestinationPath $stage
        Assert-InstalledInputs -ProjectRoot $stage -Manifest $Manifest
        New-Item -ItemType Directory -Path (Split-Path -Parent $projectRoot) -Force |
            Out-Null
        Move-Item -LiteralPath $stage -Destination $projectRoot
        $marker = [ordered]@{
            release_id = [string]$Manifest.release_id
            project_sha256 = [string]$Manifest.project.sha256
        } | ConvertTo-Json -Compress
        [IO.File]::WriteAllText($markerPath, $marker)
    }

    Copy-VerifiedDatasets -PackagePath $PackagePath -ProjectRoot $projectRoot `
        -Manifest $Manifest
    return $projectRoot
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )

    & $Executable @Arguments
    $nativeExit = $LASTEXITCODE
    if ($nativeExit -ne 0) {
        throw "$Label falhou com codigo $nativeExit."
    }
}

function Invoke-Install {
    param(
        [Parameter(Mandatory = $true)][string]$PackagePath,
        [Parameter(Mandatory = $true)][string]$InstallPath,
        [Parameter(Mandatory = $true)][string]$LaunchPath,
        [switch]$OnlyValidate,
        [switch]$OnlyPlan,
        [string]$ProbeJson = ''
    )

    if ($OnlyValidate -and $OnlyPlan) {
        throw 'Use somente ValidateOnly ou PlanOnly, nao ambos.'
    }
    $plan = Test-OfflinePreflight -PackagePath $PackagePath -InstallPath $InstallPath `
        -LaunchPath $LaunchPath -ProbeJson $ProbeJson
    if ($OnlyValidate) {
        Write-Output 'PAYLOAD_OK'
        return
    }
    if ($OnlyPlan) {
        $publicPlan = [ordered]@{
            release_id = $plan.release_id
            python_version = $plan.python_version
            package_root = $plan.package_root
            install_root = $plan.install_root
            project_root = $plan.project_root
            launch_dir = $plan.launch_dir
            launch_dir_writable = $plan.launch_dir_writable
            available_bytes = $plan.available_bytes
            required_bootstrap_bytes = $plan.required_bootstrap_bytes
        }
        Write-Output ($publicPlan | ConvertTo-Json -Compress)
        return
    }

    New-Item -ItemType Directory -Path $plan.install_root -Force | Out-Null
    $downloadRoot = Join-Path $plan.install_root 'downloads'
    $uvPin = $plan.manifest.tools.uv
    Write-Output '[1/4] Obtendo uv 0.12.3 verificado...'
    $uvArchive = Get-VerifiedDownload -Url ([string]$uvPin.url) `
        -Sha256 ([string]$uvPin.sha256) -SizeBytes ([int64]$uvPin.size_bytes) `
        -DownloadRoot $downloadRoot
    $uvExe = Install-VerifiedUv -ArchivePath $uvArchive -InstallRoot $plan.install_root `
        -ExpectedArchiveSha256 ([string]$uvPin.sha256)

    $pythonRoot = Join-Path $plan.install_root 'runtime\python'
    $env:UV_PYTHON_INSTALL_DIR = $pythonRoot
    $env:UV_CACHE_DIR = Join-Path $plan.install_root 'cache\uv'
    Write-Output '[2/4] Preparando CPython 3.12.13...'
    Invoke-NativeChecked -Executable $uvExe -Label 'uv python install' -Arguments @(
        'python', 'install', '3.12.13', '--managed-python', '--install-dir', $pythonRoot
    )

    Write-Output '[3/4] Extraindo projeto e sincronizando dependencias fixadas...'
    $projectRoot = Prepare-Project -PackagePath $plan.package_root `
        -InstallRoot $plan.install_root -Manifest $plan.manifest
    Invoke-NativeChecked -Executable $uvExe -Label 'uv sync' -Arguments @(
        '--directory', $projectRoot, 'sync', '--frozen', '--no-dev',
        '--managed-python', '--python', '3.12.13'
    )

    $orchestrator = Join-Path $projectRoot 'scripts\windows_benchmark.py'
    if (-not (Test-Path -LiteralPath $orchestrator -PathType Leaf)) {
        throw 'Orquestrador scripts/windows_benchmark.py ausente na release.'
    }
    $stateRoot = Join-Path $plan.install_root 'state'
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    $bootstrapReceipt = Join-Path $stateRoot 'bootstrap-receipt.json'
    Write-Output '[4/4] Iniciando benchmark de predio e casa...'
    Invoke-NativeChecked -Executable $uvExe -Label 'benchmark Windows' -Arguments @(
        '--directory', $projectRoot, 'run', '--frozen', '--no-dev',
        '--managed-python', '--python', '3.12.13', 'python', $orchestrator,
        '--manifest', (Join-Path $plan.package_root 'release-manifest.json'),
        '--package-root', $plan.package_root,
        '--launch-dir', $plan.launch_dir,
        '--bootstrap-receipt', $bootstrapReceipt
    )
}

$exitCode = 0
$launchDirectory = (Get-Location).Path
try {
    Invoke-Install -PackagePath $PackageRoot -InstallPath $AppRoot `
        -LaunchPath $launchDirectory -OnlyValidate:$ValidateOnly -OnlyPlan:$PlanOnly `
        -ProbeJson $TestProbeJson
}
catch [OperationCanceledException] {
    $exitCode = 130
    [Console]::Error.WriteLine('ERRO: benchmark interrompido pelo operador.')
}
catch {
    $exitCode = 1
    [Console]::Error.WriteLine("ERRO: $($_.Exception.Message)")
}
finally {
    # Reservado para limpeza cooperativa do MVP; caches verificados sao preservados.
}

exit $exitCode
