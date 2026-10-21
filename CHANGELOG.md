# Zmiany

Numeracja wersji: `X.Y.Z`. Wydanie na GitHubie powstaje automatycznie po zmianie wersji w
`custom_components/ha_opencarwings/manifest.json` na gałęzi `main`, a jego opis to odpowiednia sekcja tego pliku.
Wersja 1.0.0 to kod z [oryginału developerfromjokela/ha_opencarwings](https://github.com/developerfromjokela/ha_opencarwings)
(commit „Fix some issues” z 29.08.2026).

## 1.0.1

- **Kod zgodny z działającą instalacją.** Do repozytorium trafiły dwie rzeczy, które do tej pory istniały tylko
  w Home Assistant autora forka:
  - `services.yaml` z opisem usługi `ha_opencarwings.refresh` (po polsku, z polem `entry_id`) – sama usługa
    była już w kodzie, brakowało jej opisu w interfejsie,
  - `manifest.json`: wymaganie `opencarwings_client@git+…` (z nazwą pakietu) zamiast samego adresu git,
    żeby pip poprawnie rozpoznawał pakiet.
- `manifest.json` bez klucza `platforms`, którego Home Assistant nie zna, i z kluczami w kolejności wymaganej
  przez hassfest. Dodany właściciel kodu `@kriskomp`, dokumentacja wskazuje na ten fork.
- **Wydania automatyczne:** po zmianie wersji w `manifest.json` na `main` GitHub Actions uruchamia testy
  i publikuje wydanie z opisem z tego pliku (HACS pokaże ją jako aktualizację). Testy (Python 3.14) oraz
  walidacja HACS/hassfest działają przy każdym PR.
