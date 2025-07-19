def has_role(groups: list[str], *roles: str) -> bool:
    return any(role in groups for role in roles)
