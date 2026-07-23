# Bulk-submits every sitemap URL to Bing via IndexNow. Run after any deploy
# that changes page content or metadata. Bing-only: Google ignores IndexNow.
#   powershell -File scripts\indexnow-ping.ps1
$ErrorActionPreference = "Stop"

$sitemapUrl = "https://www.fabricdemogallery.com/sitemap.xml"
$key = "962e1dc3f07a54b8"  # must match frontend/public/962e1dc3f07a54b8.txt

[xml]$sitemap = (Invoke-WebRequest -Uri $sitemapUrl -UseBasicParsing).Content
$urls = @($sitemap.urlset.url.loc)
Write-Host "Submitting $($urls.Count) URLs from sitemap..."

$body = @{
    host        = "www.fabricdemogallery.com"
    key         = $key
    keyLocation = "https://www.fabricdemogallery.com/$key.txt"
    urlList     = $urls
} | ConvertTo-Json

$resp = Invoke-WebRequest -Uri "https://api.indexnow.org/indexnow" -Method Post `
    -ContentType "application/json; charset=utf-8" -Body $body -UseBasicParsing
Write-Host "IndexNow response: HTTP $($resp.StatusCode)"
