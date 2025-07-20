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

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_staff(self):
        return "Admin" in self.groups

    @property
    def is_active(self):
        return True

    def has_perm(self, perm, obj=None):
        return False

    def has_module_perms(self, app_label):
        return False

    def has_group(self, group_name):
        return group_name in self.groups

    def get_group_permissions(self, obj=None):
        return set()

    def get_username(self):
        return self.matricula