from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve   # ⭐ for production media serving
from admissions.views import custom_404  # ⭐ your custom 404 view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('admissions.urls')),
]

# ⭐ Serve static and media files only when DEBUG=True
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # ⭐ In production, WhiteNoise serves static files, but media files need this:
    urlpatterns += [
        path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
    ]

# ⭐ Custom 404 handler – hides the URL list from users
handler404 = custom_404