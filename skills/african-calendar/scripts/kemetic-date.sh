#!/usr/bin/env bash
# Computes dates in the "Calendrier Africain Kamit" system used by
# https://calendrier-africain.netlify.app/ — pure arithmetic, no network call.
#
# Formula reverse-engineered from that page's own inline Vue script
# (fetched + inspected 2026-09-07): fixed 365-day year, no leap years —
# epoch An 6262, Mois 1, Jour 1 = 2025-08-02 (local time). The Gregorian
# calendar is the one that drifts (leap years); this one never does. If the
# site's own formula ever changes, this drifts from it — spot-check against
# the live page occasionally rather than trusting this blindly forever.
#
# Usage:
#   kemetic-date.sh                    → Kemetic date for today
#   kemetic-date.sh YYYY-MM-DD          → Kemetic date for that Gregorian date
#   kemetic-date.sh --to-gregorian Y M D → Gregorian date for that Kemetic Y/M/D (month 1-12)
#
# Output (forward): "<day> <month name>, <ordinal> Month of the <period-en> (<period-fr>), Year <year> — mois de <god>"
#              or, on one of the 5 yearly épagomènes: "Épagomène <name> (<deity>), Year <year>"
# Output (--to-gregorian): a plain YYYY-MM-DD
set -euo pipefail

MONTHS=(
  "Thout|Akhet|Flood|Thot"
  "Phaophi|Akhet|Flood|Amon"
  "Athyr|Akhet|Flood|Hathor"
  "Khoiak|Akhet|Flood|Sokar"
  "Tybi|Peret|Recession|Sekhmet"
  "Méchir|Peret|Recession|Min"
  "Phamenoth|Peret|Recession|Amenhotep"
  "Pharmouti|Peret|Recession|Rennoutet"
  "Pachon|Chémou|Harvest|Khonsou"
  "Payni|Chémou|Harvest|Rê"
  "Epiphi|Chémou|Harvest|Horus"
  "Mésori|Chémou|Harvest|Rê"
)
EPAG_NAMES=(Wasire Hor Setou Aïssate Nabintou)
EPAG_DEITIES=(Osiris Horus Seth Isis Nephthys)

BASE="2025-08-02 00:00:00"
BASE_EPOCH=$(date -d "$BASE" +%s)

ordinal() { case "$1" in 1) echo "1st";; 2) echo "2nd";; 3) echo "3rd";; 4) echo "4th";; esac; }

kemetic_for_epoch() {
  local now_epoch="$1"
  local diff_days=$(( (now_epoch - BASE_EPOCH) / 86400 ))
  local year=$(( 6262 + diff_days / 365 ))
  local rem=$(( ((diff_days % 365) + 365) % 365 ))
  if [ "$rem" -lt 360 ]; then
    local month=$(( rem / 30 + 1 ))
    local day=$(( rem % 30 + 1 ))
    IFS='|' read -r mname mperiod_fr mperiod_en mgod <<< "${MONTHS[$((month-1))]}"
    local rank=$(( (month - 1) % 4 + 1 ))
    echo "${day} ${mname}, $(ordinal "$rank") Month of the ${mperiod_en} (${mperiod_fr}), Year ${year} — mois de ${mgod}"
  else
    local idx=$(( rem - 360 ))
    echo "Épagomène ${EPAG_NAMES[$idx]} (${EPAG_DEITIES[$idx]}), Year ${year}"
  fi
}

if [ "${1:-}" = "--to-gregorian" ]; then
  year="$2"; month="$3"; day="$4"
  offset_days=$(( (year - 6262) * 365 + (month - 1) * 30 + (day - 1) ))
  date -d "@$(( BASE_EPOCH + offset_days * 86400 ))" +%Y-%m-%d
elif [ $# -eq 1 ]; then
  kemetic_for_epoch "$(date -d "$1 00:00:00" +%s)"
else
  kemetic_for_epoch "$(date +%s)"
fi
