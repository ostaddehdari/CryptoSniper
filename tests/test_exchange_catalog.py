from decimal import Decimal

import pytest
from apps.exchanges.models import Asset, Exchange, ExchangeMarket, UserExchangeAccount
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_catalog_rejects_unsupported_market_and_futures_only_account(django_user_model):
    owner = django_user_model.objects.create_user(username="catalog-owner")
    exchange = Exchange.objects.create(
        code="spot-only", name="Spot only", adapter_code="spot-only", margin_supported=False
    )
    base = Asset.objects.create(symbol="BTC")
    quote = Asset.objects.create(symbol="USDT")
    with pytest.raises(ValidationError):
        ExchangeMarket.objects.create(
            exchange=exchange,
            symbol="BTC/USDT",
            base_asset=base,
            quote_asset=quote,
            market_type=ExchangeMarket.MarketType.MARGIN,
        )
    unsupported = Exchange.objects.create(
        code="future-only",
        name="Future only",
        adapter_code="future-only",
        spot_supported=False,
        margin_supported=False,
        futures_supported=True,
    )
    account = UserExchangeAccount(owner=owner, exchange=unsupported, label="نباید ذخیره شود")
    with pytest.raises(ValidationError):
        account.save()


@pytest.mark.django_db
def test_spot_market_cannot_claim_leverage():
    exchange = Exchange.objects.create(
        code="strict-spot", name="Strict spot", adapter_code="strict-spot"
    )
    base = Asset.objects.create(symbol="ETH")
    quote = Asset.objects.create(symbol="USDC")
    market = ExchangeMarket(
        exchange=exchange,
        symbol="ETH/USDC",
        base_asset=base,
        quote_asset=quote,
        market_type=ExchangeMarket.MarketType.SPOT,
        max_leverage=Decimal("2"),
    )
    with pytest.raises(ValidationError):
        market.save()


@pytest.mark.django_db
def test_user_exchange_accounts_are_owner_scoped(django_user_model):
    one = django_user_model.objects.create_user(username="owner-one")
    two = django_user_model.objects.create_user(username="owner-two")
    exchange = Exchange.objects.create(
        code="owner-test", name="Owner test", adapter_code="owner-test"
    )
    account = UserExchangeAccount.objects.create(owner=one, exchange=exchange, label="اصلی")
    assert list(UserExchangeAccount.objects.for_user(one)) == [account]
    assert not UserExchangeAccount.objects.for_user(two).exists()
