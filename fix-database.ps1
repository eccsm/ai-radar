# PowerShell script to create both databases
Write-Host "Creating ai and ai_radar databases..."

# Create the databases directly via Docker exec
docker exec -i ai-radar-db-1 psql -U ai -c "CREATE DATABASE ai WITH OWNER ai;" postgres
docker exec -i ai-radar-db-1 psql -U ai -c "CREATE DATABASE ai_radar WITH OWNER ai;" postgres

Write-Host "Done! Both databases should now exist."
