#!/usr/bin/env bash
# prove_isolation.sh
set -euo pipefail

PVR_URL="http://localhost:8000"
AGS_URL="http://localhost:8001"
PVR_DB="$HOME/Documents/Harisankar/Projects/pvr-app/backend/pvr.db"
AGS_DB="$HOME/Documents/Harisankar/Projects/ags-app/backend/ags.db"
VYHBZ_DB="postgresql://postgres:postgres@localhost:5436/core_local"

echo "=== 1. HTTP: each chain responds independently ==="
echo "PVR /v1/showtimes count: $(curl -s "$PVR_URL/v1/showtimes" | jq 'length')"
echo "AGS /v1/showtimes count: $(curl -s "$AGS_URL/v1/showtimes" | jq 'length')"

echo
echo "=== 2. HTTP: AGS-specific cinema must exist in AGS and only there ==="
echo "AGS /v1/showtimes cinemas:"
curl -s "$AGS_URL/v1/showtimes" | jq -r '.[].cinema_name' | sort -u
echo "PVR /v1/showtimes cinemas:"
curl -s "$PVR_URL/v1/showtimes" | jq -r '.[].cinema_name' | sort -u

echo
echo "=== 3. DB: AGS cinema name in AGS DB ==="
sqlite3 "$AGS_DB" "SELECT COUNT(*) FROM cinemas WHERE name LIKE '%T. Nagar%'"
echo "=== DB: AGS cinema name in PVR DB (should be 0) ==="
sqlite3 "$PVR_DB" "SELECT COUNT(*) FROM cinemas WHERE name LIKE '%T. Nagar%'"

echo
echo "=== 4. DB: cinema + showtime counts per chain ==="
echo -n "PVR cinemas: "; sqlite3 "$PVR_DB" "SELECT COUNT(*) FROM cinemas"
echo -n "PVR showtimes: "; sqlite3 "$PVR_DB" "SELECT COUNT(*) FROM showtimes"
echo -n "AGS cinemas: "; sqlite3 "$AGS_DB" "SELECT COUNT(*) FROM cinemas"
echo -n "AGS showtimes: "; sqlite3 "$AGS_DB" "SELECT COUNT(*) FROM showtimes"

echo
echo "=== 5. Vyhbz: provider-scoped showtime counts ==="
psql "$VYHBZ_DB" -c "
SELECT pr.name AS provider, COUNT(s.id) AS showtimes
FROM provider_registry pr
LEFT JOIN showtimes s ON s.provider_id = pr.id
GROUP BY pr.name ORDER BY pr.name;
"

echo
echo "=== 6. Vyhbz: Chennai venues, grouped by provider ==="
psql "$VYHBZ_DB" -c "
SELECT pr.name AS provider, v.name AS venue, COUNT(s.id) AS showtimes
FROM venues v
JOIN screens sc ON sc.venue_id = v.id
JOIN showtimes s ON s.screen_id = sc.id
JOIN provider_registry pr ON pr.id = s.provider_id
WHERE v.city = 'Chennai'
GROUP BY pr.name, v.name ORDER BY pr.name, v.name;
"
