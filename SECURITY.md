# Sicurezza

- Il server gira solo in locale su stdio; non apre porte e non accetta connessioni di rete.
- Nessuna credenziale Betfair, nessun accesso al database Pickfair, nessuna chiamata a Betfair.
- La futura Control API sarà raggiungibile solo su IP loopback letterale con porta esplicita.
- Nessun segreto nel repository: test automatici bloccano contenuti e file con forma di segreto.
- Log di audit su stderr con allowlist dei campi; messaggi di errore fissi.
- Il contenuto restituito dalla Control API è trattato come dato, mai come istruzione.

Segnalazioni: aprire una issue privata al proprietario del repository; non includere
segreti o dati di conto nella segnalazione.
