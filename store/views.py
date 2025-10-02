from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from .models import Medicine, Order, OrderItem
from decimal import Decimal
import json

def home(request):
    medicines = Medicine.objects.all().order_by('-created_at')[:12]
    
    query = request.GET.get('q', '')
    if query:
        medicines = Medicine.objects.filter(
            Q(name__icontains=query) | 
            Q(company_name__icontains=query) |
            Q(components__icontains=query)
        )
    
    return render(request, 'home.html', {'medicines': medicines, 'query': query})

def medicine_detail(request, medicine_id):
    medicine = get_object_or_404(Medicine, id=medicine_id)
    return render(request, 'product_detail.html', {'medicine': medicine})

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')

@login_required
def profile_view(request):
    orders = Order.objects.filter(user=request.user, is_completed=True).order_by('-order_date')
    return render(request, 'profile.html', {'orders': orders})

def get_cart(request):
    cart = request.session.get('cart', {})
    return cart

def save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True

@login_required
def add_to_cart(request, medicine_id):
    if request.method == 'POST':
        medicine = get_object_or_404(Medicine, id=medicine_id)
        cart = get_cart(request)
        
        medicine_id_str = str(medicine_id)
        if medicine_id_str in cart:
            cart[medicine_id_str]['quantity'] += 1
        else:
            cart[medicine_id_str] = {
                'name': medicine.name,
                'price': str(medicine.price),
                'quantity': 1,
                'image': medicine.image.url if medicine.image else '',
                'max_quantity': medicine.quantity
            }
        
        save_cart(request, cart)
        messages.success(request, f'{medicine.name} added to cart!')
        return redirect('cart_view')
    
    return redirect('medicine_detail', medicine_id=medicine_id)

@login_required
def cart_view(request):
    cart = get_cart(request)
    cart_items = []
    total = Decimal('0.00')
    
    for medicine_id, item in cart.items():
        item_total = Decimal(item['price']) * item['quantity']
        cart_items.append({
            'id': medicine_id,
            'medicine': get_object_or_404(Medicine, id=medicine_id),
            'quantity': item['quantity'],
            'price': item['price'],
            'total': item_total,
            'image': item['image']
        })
        total += item_total
    
    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total': total
    })

@login_required
def update_cart(request, medicine_id):
    if request.method == 'POST':
        cart = get_cart(request)
        medicine_id_str = str(medicine_id)
        
        if medicine_id_str in cart:
            quantity = int(request.POST.get('quantity', 1))
            medicine = get_object_or_404(Medicine, id=medicine_id)
            
            if quantity <= 0:
                del cart[medicine_id_str]
                messages.info(request, 'Item removed from cart.')
            elif quantity <= medicine.quantity:
                cart[medicine_id_str]['quantity'] = quantity
                messages.success(request, 'Cart updated!')
            else:
                messages.error(request, f'Only {medicine.quantity} available in stock.')
        
        save_cart(request, cart)
    
    return redirect('cart_view')

@login_required
def remove_from_cart(request, medicine_id):
    if request.method == 'POST':
        cart = get_cart(request)
        medicine_id_str = str(medicine_id)
        
        if medicine_id_str in cart:
            del cart[medicine_id_str]
            save_cart(request, cart)
            messages.info(request, 'Item removed from cart.')
    
    return redirect('cart_view')

from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.utils import timezone

@login_required
def checkout_view(request):
    cart = get_cart(request)
    if not cart:
        messages.warning(request, 'Your cart is empty!')
        return redirect('cart_view')
    
    cart_items = []
    total = Decimal('0.00')
    
    for medicine_id, item in cart.items():
        medicine = get_object_or_404(Medicine, id=medicine_id)
        if item['quantity'] > medicine.quantity:
            messages.error(request, f'Not enough stock for {medicine.name}. Only {medicine.quantity} available.')
            return redirect('cart_view')
        
        item_total = Decimal(item['price']) * item['quantity']
        cart_items.append({
            'medicine': medicine,
            'quantity': item['quantity'],
            'price': item['price'],
            'total': item_total
        })
        total += item_total
    
    discount_percentage = Decimal('0')
    final_amount = total

    if request.method == 'POST':
        # Only allow discount if user is staff/admin
        if request.user.is_staff:
            discount_percentage = Decimal(request.POST.get('discount', '0'))
            discount_amount = total * (discount_percentage / Decimal('100'))
            final_amount = total - discount_amount

        try:
            with transaction.atomic():
                # Create order
                order = Order.objects.create(
                    user=request.user,
                    total_amount=total,
                    discount_percentage=discount_percentage,
                    final_amount=final_amount,
                    is_completed=True
                )
                
                # Create order items and update medicine quantities
                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        medicine=item['medicine'],
                        quantity=item['quantity'],
                        price=item['price']
                    )
                    item['medicine'].quantity -= item['quantity']
                    item['medicine'].save()
                
                # Clear cart
                request.session['cart'] = {}
                request.session.modified = True
                
                messages.success(request, f'Order placed successfully! Total: ₹{final_amount:.2f}')
                return redirect('order_success', order_id=order.id)
                
        except Exception as e:
            messages.error(request, 'An error occurred during checkout. Please try again.')
    
    return render(request, 'checkout.html', {
        'cart_items': cart_items,
        'total': total,
        'final_amount': final_amount,
        'discount_percentage': discount_percentage,
        'now': timezone.now()  # pass current date/time for billing
    })
@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'order_success.html', {'order': order})

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from .forms import MedicineForm

@staff_member_required
def add_product(request):
    if request.method == 'POST':
        form = MedicineForm(request.POST, request.FILES)
        if form.is_valid():
            medicine = form.save()
            messages.success(request, f'Medicine "{medicine.name}" added successfully!')
            return redirect('add_product')
    else:
        form = MedicineForm()
    
    return render(request, 'add_product.html', {'form': form})
from django.shortcuts import redirect
from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def redirect_to_medicine_admin(request):
    return redirect('admin:store_medicine_changelist')
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Medicine
from .forms import MedicineForm
import json

@staff_member_required
def admin_product_management(request):
    """Comprehensive product management page for admin"""
    medicines = Medicine.objects.all().order_by('-created_at')
    form = MedicineForm()
    
    return render(request, 'admin_product_management.html', {
        'medicines': medicines,
        'form': form,
        'title': 'Product Management'
    })

@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def api_update_medicine(request, medicine_id):
    """API endpoint to update medicine details"""
    medicine = get_object_or_404(Medicine, id=medicine_id)
    
    try:
        data = json.loads(request.body)
        
        # Update fields if they exist in the request
        if 'quantity' in data:
            medicine.quantity = int(data['quantity'])
        if 'price' in data:
            medicine.price = float(data['price'])
        if 'name' in data:
            medicine.name = data['name']
        if 'company_name' in data:
            medicine.company_name = data['company_name']
        if 'power' in data:
            medicine.power = data['power']
        
        medicine.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Medicine updated successfully',
            'medicine': {
                'id': medicine.id,
                'name': medicine.name,
                'company_name': medicine.company_name,
                'power': medicine.power,
                'price': str(medicine.price),
                'quantity': medicine.quantity
            }
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def api_add_medicine(request):
    """API endpoint to add a new medicine"""
    form = MedicineForm(request.POST, request.FILES)
    
    if form.is_valid():
        medicine = form.save()
        return JsonResponse({
            'status': 'success',
            'message': 'Medicine added successfully',
            'medicine': {
                'id': medicine.id,
                'name': medicine.name,
                'company_name': medicine.company_name,
                'power': medicine.power,
                'price': str(medicine.price),
                'quantity': medicine.quantity,
                'image_url': medicine.image.url if medicine.image else ''
            }
        })
    else:
        return JsonResponse({
            'status': 'error',
            'message': 'Form validation failed',
            'errors': form.errors
        }, status=400)

@staff_member_required
@csrf_exempt
@require_http_methods(["DELETE"])
def api_delete_medicine(request, medicine_id):
    """API endpoint to delete a medicine"""
    medicine = get_object_or_404(Medicine, id=medicine_id)
    medicine_name = medicine.name
    medicine.delete()
    
    return JsonResponse({
        'status': 'success',
        'message': f'Medicine "{medicine_name}" deleted successfully'
    })
from django.shortcuts import render, get_object_or_404
from .models import Medicine
import requests

def medicine_detail(request, medicine_id):
    medicine = get_object_or_404(Medicine, id=medicine_id)
    
    medicine_info = {
        "description": "No information available from FDA database",
        "uses": "No information available from FDA database", 
        "side_effects": "No information available from FDA database",
        "precautions": "No information available from FDA database",
    }

    try:
        # Try FDA API with the medicine name
        url = f'https://api.fda.gov/drug/label.json?search=openfda.brand_name:"{medicine.name}"&limit=1'
        print(f"🔍 API URL: {url}")
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("results"):
                result = data["results"][0]
                print("✅ FDA API returned data")
                print(f"🔑 Available keys: {list(result.keys())}")
                
                # Extract description from various possible fields
                if result.get("description"):
                    medicine_info["description"] = result["description"][0]
                elif result.get("purpose"):
                    medicine_info["description"] = result["purpose"][0]
                elif result.get("clinical_pharmacology"):
                    medicine_info["description"] = result["clinical_pharmacology"][0]
                
                # Extract uses
                if result.get("indications_and_usage"):
                    medicine_info["uses"] = result["indications_and_usage"][0]
                elif result.get("purpose"):
                    medicine_info["uses"] = result["purpose"][0]
                
                # EXTRACT SIDE EFFECTS - ENHANCED
                if result.get("adverse_reactions"):
                    medicine_info["side_effects"] = result["adverse_reactions"][0]
                elif result.get("warnings"):
                    medicine_info["side_effects"] = result["warnings"][0]
                elif result.get("boxed_warning"):
                    medicine_info["side_effects"] = result["boxed_warning"][0]
                elif result.get("contraindications"):
                    medicine_info["side_effects"] = result["contraindications"][0]
                elif result.get("drug_interactions"):
                    medicine_info["side_effects"] = result["drug_interactions"][0]
                # If still no side effects, use a generic message
                elif medicine_info["side_effects"] == "No information available from FDA database":
                    medicine_info["side_effects"] = "Common side effects may include nausea, headache, or dizziness. Consult your doctor for specific side effects."
                
                # Extract precautions
                if result.get("precautions"):
                    medicine_info["precautions"] = result["precautions"][0]
                elif result.get("warnings"):
                    medicine_info["precautions"] = result["warnings"][0]
                elif result.get("drug_interactions"):
                    medicine_info["precautions"] = result["drug_interactions"][0]
                elif result.get("contraindications"):
                    medicine_info["precautions"] = result["contraindications"][0]
                    
                print(f"📊 Extracted data - Description: {bool(result.get('description'))}, Uses: {bool(result.get('indications_and_usage'))}, Side Effects: {bool(result.get('adverse_reactions'))}, Precautions: {bool(result.get('precautions'))}")
                    
            else:
                print("❌ No results in FDA API response")
        else:
            print(f"❌ FDA API returned status: {response.status_code}")
            
    except Exception as e:
        print(f"💥 Error calling FDA API: {e}")

    context = {
        'medicine': medicine,
        'medicine_info': medicine_info,
    }
    return render(request, 'product_detail.html', context)


