from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('search/', views.search_view, name='search'),
    path('admission/', views.admission_form, name='admission_form'),
    path('success/<int:student_id>/', views.success_view, name='success'),
    path('pay/<int:student_id>/', views.mock_payment, name='mock_payment'),

    # ---- Student password ----
    path('set-password/<str:token>/', views.set_password, name='set_password'),
    path('set-password-request/', views.student_password_setup_request, name='student_password_setup_request'),

    # ---- Student portal ----
    path('track/', views.student_login, name='student_login'),
    path('profile/', views.student_profile, name='student_profile'),
    path('track/logout/', views.student_logout, name='student_logout'),

    # ---- Payment receipt ----
    path('receipt/<str:app_id>/', views.payment_receipt, name='payment_receipt'),

    # ---- Admin panel ----
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('admin-panel/verify/<int:student_id>/', views.admin_verify, name='admin_verify'),
    path('admin-panel/reject/<int:student_id>/', views.admin_reject, name='admin_reject'),
    path('admin-panel/login/', views.admin_login, name='admin_login'),
    path('admin-panel/verify-otp/', views.verify_otp, name='admin_otp'),
    path('admin-panel/logout/', views.admin_logout, name='admin_logout'),

    # ---- Admin announcements ----
    path('admin-panel/announcements/', views.announcement_list, name='announcement_list'),
    path('admin-panel/announcements/<int:announcement_id>/toggle/', views.announcement_toggle, name='announcement_toggle'),
    path('admin-panel/announcements/<int:announcement_id>/delete/', views.announcement_delete, name='announcement_delete'),
    path('admin-panel/announcements/create/', views.announcement_create, name='announcement_create'),

    # ---- Search Autocomplete ----
    path('autocomplete/', views.autocomplete_search, name='autocomplete_search'),

    # ---- Contact page ----
    path('contact/', views.contact, name='contact'),
]
