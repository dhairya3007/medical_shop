from django.contrib import admin
from .models import Medicine, Order, OrderItem
from django.utils.html import format_html

class MedicineAdmin(admin.ModelAdmin):
    list_display = ['name', 'company_name', 'power', 'price', 'quantity', 'image_preview', 'created_at']
    list_filter = ['company_name', 'created_at']
    search_fields = ['name', 'company_name', 'product_number']
    readonly_fields = ['image_preview', 'created_at']
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" />', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Image Preview'

admin.site.register(Medicine, MedicineAdmin)
admin.site.register(Order)
admin.site.register(OrderItem)