from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions
from jose import jwt, JWTError

SECRET_KEY = "django-insecure-f=td$@o*6$utz@_2kvjf$zss#*r_8f74whhgo9y#p7rz@t*ii("
ALGORITHM = "HS256"

class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

            user_matricula = payload.get("matricula")
            campus = payload.get("campus")
            groups = payload.get("groups", [])

            if user_matricula is None or campus is None:
                raise exceptions.AuthenticationFailed("Token com dados incompletos.")

            user = JWTUser(user_matricula, campus, groups)

            return (user, token)

        except JWTError:
            raise exceptions.AuthenticationFailed("Token inválido ou expirado.")

class JWTUser:
    def __init__(self, matricula, campus, groups):
        self.matricula = matricula
        self.campus = campus
        self.groups = groups