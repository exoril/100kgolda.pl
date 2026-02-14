Aby uruchomić projekt:

1. Odpal pocketbase w terminalu za pomocą komendy:
./pocketbase serve --http="127.0.0.1:8090"

Tymczasowe passy:
    marcinjakubgolda@gmail.com
    KochamPocketBase123!

2. W osobnym terminalu:
./venv/Scripts/Activate
uvicorn main:app --reload

Gotowe

Dostęp SSH do panelu admina:
ssh -L 8090:127.0.0.1:8090 USER@IP_SERWERA (nie testowane jeszcze)