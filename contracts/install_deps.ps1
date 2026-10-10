# Reproducible install of the pinned Solidity dependencies of contracts/ (no git submodules in the app repo).
# Each dependency is cloned at an exact tag and the resolved commit is VERIFIED before use.
#   powershell -ExecutionPolicy Bypass -File contracts\install_deps.ps1
$ErrorActionPreference = 'Stop'
$lib = Join-Path $PSScriptRoot 'lib'
New-Item -ItemType Directory -Force -Path $lib | Out-Null
$deps = @(
  @{ name = 'forge-std'; repo = 'https://github.com/foundry-rs/forge-std'; tag = 'v1.17.0'; sha = 'f3dae6e6ee' },
  @{ name = 'openzeppelin-contracts'; repo = 'https://github.com/OpenZeppelin/openzeppelin-contracts'; tag = 'v5.6.1'; sha = '5fd1781b14' },
  @{ name = 'morpho-blue'; repo = 'https://github.com/morpho-org/morpho-blue'; tag = 'v1.0.0'; sha = '55d2d99304' }
)
foreach ($d in $deps) {
  $dst = Join-Path $lib $d.name
  if (-not (Test-Path (Join-Path $dst '.git'))) {
    git -c advice.detachedHead=false clone --quiet --depth 1 --branch $d.tag $d.repo $dst
    if ($LASTEXITCODE -ne 0) { throw "clone failed: $($d.name)" }
  }
  $head = (git -C $dst rev-parse HEAD).Trim()
  if (-not $head.StartsWith($d.sha)) { throw "$($d.name): HEAD $head does not match pinned $($d.sha)" }
  Write-Output ("{0,-24} {1,-8} {2}" -f $d.name, $d.tag, $head)
}
