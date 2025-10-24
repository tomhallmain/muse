# PowerShell script to install AudioDevice module for audio device switching
# Run this script as Administrator if needed

Write-Host "AudioDevice Module Installer" -ForegroundColor Green
Write-Host "=============================" -ForegroundColor Green
Write-Host ""

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")

if (-not $isAdmin) {
    Write-Host "Warning: Not running as Administrator" -ForegroundColor Yellow
    Write-Host "Some operations may require elevated privileges" -ForegroundColor Yellow
    Write-Host ""
}

# Check if AudioDevice module is already installed
Write-Host "Checking for AudioDevice module..." -ForegroundColor Cyan
try {
    Import-Module AudioDevice -ErrorAction Stop
    Write-Host "✓ AudioDevice module is already installed!" -ForegroundColor Green
    Write-Host ""
    
    # Test the module
    Write-Host "Testing AudioDevice module..." -ForegroundColor Cyan
    $devices = Get-AudioDevice -List
    Write-Host "✓ Found $($devices.Count) audio devices" -ForegroundColor Green
    
    # Show current default device
    $defaultDevice = Get-AudioDevice -Default
    Write-Host "Current default device: $($defaultDevice.Name)" -ForegroundColor Green
    Write-Host ""
    Write-Host "AudioDevice module is ready to use!" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "✗ AudioDevice module not found" -ForegroundColor Red
    Write-Host ""
}

# Try to install the module
Write-Host "Installing AudioDevice module..." -ForegroundColor Cyan
try {
    # Try to install from PowerShell Gallery
    Install-Module -Name AudioDevice -Force -Scope CurrentUser -ErrorAction Stop
    Write-Host "✓ AudioDevice module installed successfully!" -ForegroundColor Green
    Write-Host ""
    
    # Test the installation
    Write-Host "Testing installation..." -ForegroundColor Cyan
    Import-Module AudioDevice -ErrorAction Stop
    $devices = Get-AudioDevice -List
    Write-Host "✓ Found $($devices.Count) audio devices" -ForegroundColor Green
    
    $defaultDevice = Get-AudioDevice -Default
    Write-Host "Current default device: $($defaultDevice.Name)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Installation complete! AudioDevice module is ready to use." -ForegroundColor Green
    
} catch {
    Write-Host "✗ Failed to install AudioDevice module" -ForegroundColor Red
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Manual installation options:" -ForegroundColor Yellow
    Write-Host "1. Run PowerShell as Administrator and try again" -ForegroundColor Yellow
    Write-Host "2. Install manually: Install-Module -Name AudioDevice -Force" -ForegroundColor Yellow
    Write-Host "3. Check PowerShell Gallery access: Test-NetConnection -ComputerName powershellgallery.com -Port 443" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Alternative: Use Windows Settings to manually switch audio devices" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Usage examples:" -ForegroundColor Cyan
Write-Host "  Get-AudioDevice -List                    # List all devices" -ForegroundColor White
Write-Host "  Get-AudioDevice -Default                 # Get current default" -ForegroundColor White
Write-Host "  Set-AudioDevice -Index 1                 # Set device by index" -ForegroundColor White
Write-Host "  Set-AudioDevice -Name 'Speakers'        # Set device by name" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to exit"
