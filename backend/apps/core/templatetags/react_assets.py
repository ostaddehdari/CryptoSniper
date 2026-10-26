from django import template

from apps.core.assets import asset_url

register = template.Library()
register.simple_tag(asset_url, name="react_asset")
