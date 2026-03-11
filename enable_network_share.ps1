[CmdletBinding()]
param(
    [string]$SharePath,
    [string]$ShareName = "POBuilderData",
    [string]$Account = "Everyone"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script in an elevated PowerShell window."
    }
}

function Enable-PrivateProfiles {
    $profiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue
    foreach ($profile in $profiles) {
        if ($profile.NetworkCategory -ne "Private") {
            Write-Host "Setting network profile '$($profile.Name)' to Private..."
            Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private
        }
    }
}

function Enable-DiscoveryAndSharing {
    Write-Host "Enabling Network Discovery firewall rules..."
    Enable-NetFirewallRule -DisplayGroup "Network Discovery" | Out-Null

    Write-Host "Enabling File and Printer Sharing firewall rules..."
    Enable-NetFirewallRule -DisplayGroup "File and Printer Sharing" | Out-Null

    $services = @("FDResPub", "fdPHost", "LanmanServer")
    foreach ($serviceName in $services) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($null -eq $service) {
            continue
        }
        if ($service.StartType -eq "Disabled") {
            Set-Service -Name $serviceName -StartupType Manual
        }
        if ($service.Status -ne "Running") {
            Write-Host "Starting service '$serviceName'..."
            Start-Service -Name $serviceName
        }
    }
}

function Ensure-ShareFolder {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "Creating folder '$Path'..."
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Ensure-SmbShare {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$UserOrGroup
    )

    $existingShare = Get-SmbShare -Name $Name -ErrorAction SilentlyContinue
    if ($null -eq $existingShare) {
        Write-Host "Creating SMB share '$Name' for '$Path'..."
        New-SmbShare -Name $Name -Path $Path -FullAccess $UserOrGroup | Out-Null
    } elseif ($existingShare.Path -ne $Path) {
        throw "Share '$Name' already exists and points to '$($existingShare.Path)'. Pick a different ShareName."
    } else {
        Write-Host "Share '$Name' already exists. Granting access for '$UserOrGroup'..."
        Grant-SmbShareAccess -Name $Name -AccountName $UserOrGroup -AccessRight Change -Force | Out-Null
    }
}

function Grant-ModifyAcl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$UserOrGroup
    )

    Write-Host "Granting NTFS Modify rights to '$UserOrGroup'..."
    $escapedPath = '"' + $Path + '"'
    $rule = "$UserOrGroup:(OI)(CI)M"
    & icacls $escapedPath /grant $rule /T | Out-Null
}

Assert-Administrator
Enable-PrivateProfiles
Enable-DiscoveryAndSharing

if ($SharePath) {
    $resolvedSharePath = [System.IO.Path]::GetFullPath($SharePath)
    Ensure-ShareFolder -Path $resolvedSharePath
    Grant-ModifyAcl -Path $resolvedSharePath -UserOrGroup $Account
    Ensure-SmbShare -Path $resolvedSharePath -Name $ShareName -UserOrGroup $Account
    Write-Host ""
    Write-Host "Share ready:"
    Write-Host "  Path: $resolvedSharePath"
    Write-Host "  UNC : \\$env:COMPUTERNAME\$ShareName"
} else {
    Write-Host ""
    Write-Host "Network discovery and file sharing are enabled."
    Write-Host "To also create a share, rerun with:"
    Write-Host "  .\enable_network_share.ps1 -SharePath C:\POBuilderData -ShareName POBuilderData -Account Everyone"
}
