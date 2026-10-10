from django import template

register = template.Library()


@register.filter
def fcfa(valeur):
    """12500 → « 12 500 FCFA » ; vide → « — »."""
    if valeur is None or valeur == '':
        return "—"
    return f"{int(valeur):,}".replace(",", "\u202f") + " FCFA"
