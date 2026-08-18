from core.models import ShopSetting

def shop_settings(request):
    return {
        'shop_settings': ShopSetting.get_settings()
    }
