#!/usr/bin/env bash
set -euo pipefail

VYHBZ_DB="postgresql://postgres:postgres@localhost:5436/core_local"
HOME_DIR="$HOME/Documents/Harisankar/Projects"

CHAINS=(
  "PVR|http://localhost:8000|$HOME_DIR/pvr-app/backend/pvr.db|PVR Lulu Mall"
  "AGS|http://localhost:8001|$HOME_DIR/ags-app/backend/ags.db|AGS T. Nagar"
  "Rakki|http://localhost:8002|$HOME_DIR/rakki-app/backend/rakki.db|Rakki Ambattur"
  "Kochi1|http://localhost:8003|$HOME_DIR/kochi-app-1/backend/kochi1.db|Cinepolis Centre Square"
  "Kochi2|http://localhost:8004|$HOME_DIR/kochi-app-2/backend/kochi2.db|Vanitha Vineetha"
  "Kochi3|http://localhost:8005|$HOME_DIR/kochi-app-3/backend/kochi3.db|Shenoys"
)

echo "======================================================================"
echo " §1  HTTP: each chain responds independently"
echo "======================================================================"
for entry in "${CHAINS[@]}"; do
  IFS='|' read -r name url db marker <<< "$entry"
  count=$(curl -s "$url/v1/showtimes" | jq 'length')
  printf "%-8s %s/v1/showtimes -> %s showtimes\n" "$name" "$url" "$count"
done

echo
echo "======================================================================"
echo " §2  DB: cinema and showtime counts per chain's own database"
echo "======================================================================"
for entry in "${CHAINS[@]}"; do
  IFS='|' read -r name url db marker <<< "$entry"
  cinemas=$(sqlite3 "$db" "SELECT COUNT(*) FROM cinemas")
  showtimes=$(sqlite3 "$db" "SELECT COUNT(*) FROM showtimes")
  printf "%-8s cinemas=%s showtimes=%s\n" "$name" "$cinemas" "$showtimes"
done

echo
echo "======================================================================"
echo " §3  Cross-DB negative: unique cinema must not appear in OTHER chains"
echo "======================================================================"
for entry in "${CHAINS[@]}"; do
  IFS='|' read -r name url db marker <<< "$entry"
  echo
  echo "--- ${name}'s unique cinema: '${marker}' ---"
  for other in "${CHAINS[@]}"; do
    IFS='|' read -r oname ourl odb omarker <<< "$other"
    if [ "$name" = "$oname" ]; then
      continue
    fi
    hit=$(sqlite3 "$odb" "SELECT COUNT(*) FROM cinemas WHERE name LIKE '%${marker}%'")
    printf "  %-20s in %-8s DB -> %s %s\n" "$marker" "$oname" "$hit" \
      "$([ "$hit" = "0" ] && echo '(isolated)' || echo 'LEAK!')"
  done
done

echo
echo "======================================================================"
echo " §4  Vyhbz: provider-scoped showtime counts"
echo "======================================================================"
psql "$VYHBZ_DB" -c "
SELECT pr.name AS provider, COUNT(s.id) AS showtimes
FROM provider_registry pr
LEFT JOIN showtimes s ON s.provider_id = pr.id
GROUP BY pr.name ORDER BY pr.name;
"

echo
echo "======================================================================"
echo " §5  Vyhbz: Chennai venues by provider"
echo "======================================================================"
psql "$VYHBZ_DB" -c "
SELECT pr.name AS provider, v.name AS venue, COUNT(s.id) AS showtimes
FROM venues v
JOIN screens sc ON sc.venue_id = v.id
JOIN showtimes s ON s.screen_id = sc.id
JOIN provider_registry pr ON pr.id = s.provider_id
WHERE v.city = 'Chennai'
GROUP BY pr.name, v.name ORDER BY pr.name, v.name;
"

echo
echo "======================================================================"
echo " §6  Vyhbz: Kochi venues by provider"
echo "======================================================================"
psql "$VYHBZ_DB" -c "
SELECT pr.name AS provider, v.name AS venue, COUNT(s.id) AS showtimes
FROM venues v
JOIN screens sc ON sc.venue_id = v.id
JOIN showtimes s ON s.screen_id = sc.id
JOIN provider_registry pr ON pr.id = s.provider_id
WHERE v.city = 'Kochi'
GROUP BY pr.name, v.name ORDER BY pr.name, v.name;
"

