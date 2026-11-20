# Interpretiertes Extraktionsschema

Schema fuer synthetische Lieferschein-Beispiele. Alle folgenden Firmen,
Produkte und Belegwerte sind erfunden.

Die rohe Notiz mischt zwei Ebenen: Felder, die einmal pro Lieferschein
vorkommen (Kopf), und Felder, die pro Artikel/Position vorkommen. Ein
Lieferschein kann mehrere Positionen haben (z.B. ein Beispiels-Schein mit Positionen
a/b).

## Kopf (einmal pro Lieferschein)

| Feld | Beispiel | Anmerkung |
| --- | --- | --- |
| Lieferant | Example Print North, Example Print South | Absender/Drucker, meist aus dem Briefkopf |
| Verlag | Example Publishing | Auftraggeber der Drucksache |
| Lieferschein-Nummer | 55078, LI26-000540 | Format variiert stark je Lieferant |
| Herkunftstext | Example Print North, Example Print South | Herkunft/Werk des Drucks |
| Datum | 30.03.2026 | nicht in der Notiz, aber praktisch immer vorhanden |

## Position (pro Artikel, 1-n pro Lieferschein)

| Feld | Beispiel | Anmerkung |
| --- | --- | --- |
| Artikelname / Titel | "Beispielroman Band 2" | zur Identifikation, oft auch ueber ISBN |
| ISBN | 9783989428362 | |
| Auflagennummer | 04 | je nach Beleg erforderlich |
| Menge | 1000, 1701 | Stück/Exemplare der Position |
| Anzahl Paletten | 2 | „Gleichpaletten" = Anzahl identisch bestückter Paletten |

## Abgeleitete Werte (nicht extrahieren, sondern berechnen)

| Wert | Herleitung | Zweck |
| --- | --- | --- |
| Anzahl Positionen | Anzahl der Positionszeilen | Plausibilitätscheck gegen das Dokument |
| Anzahl Menge (gesamt) | Summe der Positionsmengen | Plausibilitätscheck |

## Offene Fragen

- Ist „Anzahl Positionen" wirklich nur die Zeilenanzahl, oder ein eigenes
  Feld auf dem Lieferschein?
- Gilt die Auflagennummer pro Position oder pro Lieferschein?
- Gilt der Verlag pro Lieferschein oder pro Position? Annahme: pro
  Lieferschein (alle Beispiel-Scans haben genau einen Verlag; Druckereien
  liefern je Auftrag). Falls Sammel-Lieferscheine mehrerer Verlage vorkommen,
  muss Verlag auf Positionsebene wandern.
- Zählen handschriftliche Korrekturen (z.B. durchgestrichene Menge mit
  Korrektur „352 Ex") als der zu extrahierende Wert? Vermutlich ja —
  Korrektur schlägt Druckwert.
