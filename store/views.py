from math import ceil
import pandas as pd
from math import sqrt
import numpy as np
import matplotlib.pyplot as plt

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import Product, ProductGallery, ReviewRating
from category.models import Category
from carts.models import CartItem
from django.db.models import Q
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

from carts.views import _cart_id
from .forms import ReviewForm
from orders.models import OrderProduct


def store(request, category_slug=None):
    categories = None
    products = None

    if category_slug != None:
        categories = get_object_or_404(Category, slug=category_slug)
        products = Product.objects.filter(category=categories, is_available=True)
        paginator = Paginator(products, 9)
        page = request.GET.get('page')
        paged_products = paginator.get_page(page)
        product_count = products.count()

    else:
        products = Product.objects.all().filter(is_available=True).order_by('id')
        paginator = Paginator(products, 9)
        page = request.GET.get('page')
        paged_products = paginator.get_page(page)
        product_count = products.count()

    context = {
        'products': paged_products,
        'product_count': product_count,
    }

    return render(request, 'store/store.html', context)


def filter_product_by_category():
    all_products = []
    product_categories = Product.objects.values('category', 'id')
    categories = {
        product['categories'] for product in product_categories
    }
    for category in categories:
        product = Product.objects.filter(categories=category)
        print(product)
        num_size = len(product)
        num_slides = num_size//4 + ceil((num_size/4) - (num_size//4))
        all_products.append([product, range(1, num_slides), num_slides])
    
    params = {
        'all_products':all_products
    }
    return params


def generate_recommendation(request):
    products = Product.objects.all()
    ratings = ReviewRating.objects.all()
    x = y = A = B = C = D = []

    #Product Data Frames
    for product in products:
        x = [product.id, product.product_name, product.images.url, product.category] 
        y+=[x]
    products_df = pd.DataFrame(y, columns=['product_id','product_name','product_category','image'])
    print("Products DataFrame")
    print(products_df)
    print(products_df.dtypes)

    #Rating Data Frames
    print(ratings)
    for item in ratings:
        A = [item.user.id, item.product, item.rating]
        B+=[A]
    ratings_df = pd.DataFrame(B, columns=['user_id','product_id','rating'])
    print("Ratings DataFrame")
    ratings_df['user_id']=ratings_df['user_id'].astype(str).astype(np.int64)
    ratings_df['product_id']=ratings_df['product_id'].astype(str).astype(np.int64)
    ratings_df['rating']=ratings_df['rating'].astype(str).astype(np.float)
    print(ratings_df)
    print(ratings_df.dtypes)

    if request.user.is_authenticated:
        user_id = request.user.id
        #select related is join statement in django.It looks for foreign key and join the table
        user_input = ReviewRating.objects.select_related('product').filter(user=user_id)
        if user_input.count() == 0:
            recommender_query = None
            user_input = None
        else:
            for item in user_input:
                C = [item.product.product_name, item.rating]
                D+=[C]
            input_products = pd.DataFrame(D, columns=['product_name','rating'])
            print("Products viewed by user dataframe")
            input_products['rating'] = input_products['rating'].astype(np.float)
            print(input_products.dtypes)

            #Filtering out the products by title
            input_id = products_df[products_df['product_name'].isin(input_products['product_name'].tolist())]
            #Then merging it so we can get the product_id. It's implicitly merging it by product title.
            input_products = pd.merge(input_id, input_products)

            print(input_products)

            #Filtering out users that have purchased product that the input has purchased and storing it
            user_subset = ratings_df[ratings_df['product_id'].isin(input_products['productd_id'].tolist())]
            print(user_subset.head())

            #Groupby creates several sub dataframes where they all have the same value in the column specified as the parameter
            user_subset_group = user_subset.groupby(['user_id'])
            
            #print(user_subset_group.get_group(7))

            #Sorting it so users with product most in common with the input will have priority
            user_subset_group = sorted(user_subset_group,  key=lambda x: len(x[1]), reverse=True)

            print(user_subset_group[0:])


            user_subset_group = user_subset_group[0:]

             #Store the Pearson Correlation in a dictionary, where the key is the user_id and the value is the coefficient
            pearson_correlation_dict = {}

        #For every user group in our subset
            for name, group in user_subset_group:
            #Let's start by sorting the input and current user group so the values aren't mixed up later on
                group = group.sort_values(by='product_id')
                input_products = input_products.sort_values(by='product_id')
                #Get the N for the formula
                nRatings = len(group)
                #Get the review scores for the movies that they both have in common
                temp_df = input_products[input_products['product_id'].isin(group['product_id'].tolist())]
                #And then store them in a temporary buffer variable in a list format to facilitate future calculations
                tempRatingList = temp_df['rating'].tolist()
                #Let's also put the current user group reviews in a list format
                tempGroupList = group['rating'].tolist()
                #Now let's calculate the pearson correlation between two users, so called, x and y
                Sxx = sum([i**2 for i in tempRatingList]) - pow(sum(tempRatingList),2)/float(nRatings)
                Syy = sum([i**2 for i in tempGroupList]) - pow(sum(tempGroupList),2)/float(nRatings)
                Sxy = sum( i*j for i, j in zip(tempRatingList, tempGroupList)) - sum(tempRatingList)*sum(tempGroupList)/float(nRatings)
                
                #If the denominator is different than zero, then divide, else, 0 correlation.
                if Sxx != 0 and Syy != 0:
                    pearson_correlation_dict[name] = Sxy/sqrt(Sxx*Syy)
                else:
                    pearson_correlation_dict[name] = 0

            print(pearson_correlation_dict.items())

            pearsonDF = pd.DataFrame.from_dict(pearson_correlation_dict, orient='index')
            pearsonDF.columns = ['similarityIndex']
            pearsonDF['user_id'] = pearsonDF.index
            pearsonDF.index = range(len(pearsonDF))
            print(pearsonDF.head())

            topUsers=pearsonDF.sort_values(by='similarityIndex', ascending=False)[0:]
            print(topUsers.head())

            topUsersRating=topUsers.merge(ratings_df, left_on='user_id', right_on='user_id', how='inner')
            topUsersRating.head()

                #Multiplies the similarity by the user's ratings
            topUsersRating['weightedRating'] = topUsersRating['similarityIndex']*topUsersRating['rating']
            topUsersRating.head()


            #Applies a sum to the topUsers after grouping it up by userId
            tempTopUsersRating = topUsersRating.groupby('product_id').sum()[['similarityIndex','weightedRating']]
            tempTopUsersRating.columns = ['sum_similarityIndex','sum_weightedRating']
            tempTopUsersRating.head()

            #Creates an empty dataframe
            recommendation_df = pd.DataFrame()
            #Now we take the weighted average
            recommendation_df['weighted average recommendation score'] = tempTopUsersRating['sum_weightedRating']/tempTopUsersRating['sum_similarityIndex']
            recommendation_df['product_id'] = tempTopUsersRating.index
            recommendation_df.head()

            recommendation_df = recommendation_df.sort_values(by='weighted average recommendation score', ascending=False)
            recommender = products_df.loc[products_df['product_id'].isin(recommendation_df.head(5)['product_id'].tolist())]
            print(recommender)
            return recommender.to_dict('records')

def recommendation_products(request):
    context = filter_product_by_category()
    context['recommended'] = generate_recommendation(request)
   
    return render(request, 'home.html', context)
    
def product_detail(request, category_slug, product_slug):
    try:
        single_product = Product.objects.get(category__slug=category_slug, slug=product_slug)
        in_cart = CartItem.objects.filter(cart__cart_id=_cart_id(request), product=single_product).exists()
    except Exception as e:
        raise e

    if request.user.is_authenticated:
        try:
            orderproduct = OrderProduct.objects.filter(user=request.user, product_id=single_product.id).exists()
        except OrderProduct.DoesNotExist:
            orderproduct = None
    else:
        orderproduct = None

    # Get the reviews
    reviews = ReviewRating.objects.filter(product_id=single_product.id, status=True)

    # Get the product gallery
    product_gallery = ProductGallery.objects.filter(product_id=single_product.id)

    context = {
        'single_product': single_product,
        'in_cart'       : in_cart,
        'orderproduct': orderproduct,
        'reviews': reviews,
        'product_gallery': product_gallery,
    }
    return render(request, 'store/product_detail.html', context)


def search(request):

    if 'keyword' in request.GET:
        keyword = request.GET['keyword']

        if keyword:
            products = Product.objects.order_by('stock').filter(Q(description__icontains=keyword) | Q(product_name__icontains=keyword))
            product_count = products.count()

    context = {
        'products': products,
        'product_count': product_count,
    }

    return render(request, 'store/store.html', context)



def submit_review(request, product_id):
    url = request.META.get('HTTP_REFERER')
    if request.method == 'POST':
        try:
            reviews = ReviewRating.objects.get(user__id=request.user.id, product__id=product_id)
            form = ReviewForm(request.POST, instance=reviews)
            form.save()
            messages.success(request, 'Thank you! Your review has been updated.')
            return redirect(url)
        except ReviewRating.DoesNotExist:
            form = ReviewForm(request.POST)
            if form.is_valid():
                data = ReviewRating()
                data.subject = form.cleaned_data['subject']
                data.rating = form.cleaned_data['rating']
                data.review = form.cleaned_data['review']
                data.ip = request.META.get('REMOTE_ADDR')
                data.product_id = product_id
                data.user_id = request.user.id
                data.save()
                messages.success(request, 'Thank you! Your review has been submitted.')
                return redirect(url)
