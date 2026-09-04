import math
def calculate_pagination_meta(total:int,page:int,limit:int)->dict:
    total_pages=math.ceil(total/limit) if limit>0 else 1
    return{
        'total':total,
        'page':page,
        'limit':limit,
        'total_pages':total_pages
    }