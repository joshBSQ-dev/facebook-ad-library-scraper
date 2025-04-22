import yaml, os, requests, csv, re
from tqdm import tqdm
from itertools import product

# Let's make it easy to bump the version in one place
API_VERSION = "v22.0"

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

assert config['search_total'] % config['page_total'] == 0, \
    "search_total should be a multiple of page_total."

# Updated field mappings for v22.0
field_mapping = {
    'ad_creation_time': 'creation_time',
    'ad_creative_body': 'body',
    'ad_creative_link_caption': 'link_caption',
    'ad_creative_link_description': 'link_description',
    'ad_creative_link_title': 'link_title',
    'ad_delivery_start_time': 'delivery_start_time',
    'ad_delivery_stop_time': 'delivery_stop_time',
    'ad_snapshot_url': 'snapshot_url',
    'demographic_distribution': 'demographic_distribution',
    'funding_entity': 'funding_entity', 
    'impressions': 'impressions',
    'page_id': 'page_id',
    'page_name': 'page_name',
    'region_distribution': 'region_distribution',
    'spend': 'spend'
}

# Map the configured fields to their v22.0 equivalents
updated_fields = [field_mapping.get(field, field) for field in config['query_fields']]

# Get the list of page IDs
page_ids = config.get('search_page_ids', [])
if not page_ids:
    page_ids = [None]  # Use None to search without a page ID if none provided

# Process each page ID separately
for page_id in page_ids:
    print(f"\n{'='*50}")
    if page_id:
        print(f"Processing page ID: {page_id}")
    else:
        print("Processing search terms (no page ID specified)")
    
    params = {
        'access_token': config['access_token'],
        'ad_reached_countries': "['US']",
        'ad_active_status': config['ad_active_status'],
        'search_terms': config.get('search_terms'),
        'fields': ",".join(updated_fields),
        'limit': config['page_total']
    }
    
    # Only add search_page_ids if we have a page_id
    if page_id:
        params['search_page_ids'] = page_id

    # Print the parameters being sent (excluding access token for security)
    print("Request parameters:")
    print({k: v for k, v in params.items() if k != 'access_token'})

    # Initialize variables
    brand_name = None
    main_file = None
    main_writer = None
    pbar = None

    try:
        for _ in range(int(config['search_total'] / config['page_total'])):
            r = requests.get(
                f'https://graph.facebook.com/{API_VERSION}/ads_archive',
                params=params)
            data = r.json()
            
            # Print a short version of the API response for debugging
            print("\nAPI Response:")
            if 'error' in data:
                print(f"Error: {data['error']}")
            elif 'data' in data:
                print(f"Retrieved {len(data['data'])} ads")
            else:
                print(data)
            
            if 'error' in data:
                print(f"API Error: {data['error']}")
                error_message = data['error'].get('message', '')
                if 'access token' in error_message and 'expired' in error_message:
                    print("\nYour Facebook access token has expired!")
                    print("You need to generate a new access token at: https://developers.facebook.com/tools/accesstoken/")
                    print("Then update the token in your config.yaml file.")
                break
                
            if 'data' not in data:
                print("No 'data' field in response. Check your access token and parameters.")
                break
            
            # If no ads were returned, skip to next page ID
            if not data['data']:
                print("No ads found for this page ID.")
                break
            
            # Get brand name from first ad if not set yet
            if not brand_name and len(data['data']) > 0 and 'page_name' in data['data'][0]:
                brand_name = data['data'][0]['page_name'].replace(' ', '_').replace("'", "")
                print(f"Creating file for brand: {brand_name}")
                
                # Create only the main ads CSV file
                main_file = open(f'{brand_name}_ads.csv', 'w', newline='', encoding='utf-8')
                main_writer = csv.DictWriter(main_file, 
                                          fieldnames=config['output_fields'],
                                          extrasaction='ignore')
                main_writer.writeheader()
            
            # Reset progress bar based on actual number of ads
            total_ads = len(data['data'])
            print(f"Processing {total_ads} ads in this batch")
            pbar = tqdm(total=total_ads, smoothing=0)
                
            for ad in data['data']:
                try:
                    # Map response fields back to expected fields
                    for old_field, new_field in field_mapping.items():
                        if new_field in ad and old_field not in ad:
                            ad[old_field] = ad[new_field]
                            
                    # Handle arrays for ad creative fields
                    if 'ad_creative_bodies' in ad and ad['ad_creative_bodies']:
                        ad['promotional_text'] = ad['ad_creative_bodies'][0]
                        
                    if 'ad_creative_link_titles' in ad and ad['ad_creative_link_titles']:
                        ad['image_name'] = ad['ad_creative_link_titles'][0]
                        
                    if 'ad_creative_link_caption' in ad and ad['ad_creative_link_caption']:
                        ad['image_link'] = ad['ad_creative_link_caption']
                        
                    if 'ad_creative_link_description' in ad and ad['ad_creative_link_description']:
                        ad['image_description'] = ad['ad_creative_link_description']
                        
                    # Convert platforms and publisher_platforms to strings if they exist
                    if 'platforms' in ad and isinstance(ad['platforms'], list):
                        ad['platforms'] = ', '.join(ad['platforms'])
                        
                    if 'publisher_platforms' in ad and isinstance(ad['publisher_platforms'], list):
                        ad['publisher_platforms'] = ', '.join(ad['publisher_platforms'])
                        
                    if 'languages' in ad and isinstance(ad['languages'], list):
                        ad['languages'] = ', '.join(ad['languages'])
                    
                    # The ad_id is encoded in the ad snapshot URL
                    # or we can use the id field directly
                    ad_id = ad.get('id', 'unknown')
                    if 'ad_snapshot_url' in ad:
                        ad_id_match = re.search(r'\d+', ad['ad_snapshot_url'])
                        if ad_id_match:
                            ad_id = ad_id_match.group(0)
                            
                    ad_url = f'https://www.facebook.com/ads/library/?id={ad_id}'

                    # Handle potentially missing fields or different field formats
                    impressions = ad.get('impressions', {})
                    if isinstance(impressions, dict):
                        impressions_min = impressions.get('lower_bound', 0)
                        impressions_max = impressions.get('upper_bound', 0)
                    else:
                        impressions_min = 0
                        impressions_max = 0
                        
                    spend = ad.get('spend', {})
                    if isinstance(spend, dict):
                        spend_min = spend.get('lower_bound', 0)
                        spend_max = spend.get('upper_bound', 0)
                    else:
                        spend_min = 0
                        spend_max = 0

                    ad.update({'ad_id': ad_id,
                              'ad_url': ad_url,
                              'impressions_min': impressions_min,
                              'impressions_max': impressions_max,
                              'spend_min': spend_min,
                              'spend_max': spend_max,
                              })

                    main_writer.writerow(ad)
                    pbar.update(1)
                except Exception as e:
                    print(f"Error processing ad {ad.get('id', 'unknown')}: {e}")
                    pbar.update(1)
                    continue

            # if we have scraped all the ads, exit
            if 'paging' not in data:
                print("No more pages to fetch.")
                break

            params.update({'after': data['paging']['cursors']['after']})
            print(f"Fetching next page of results...")

    finally:
        # Close the main file if it exists
        if main_file:
            main_file.close()

        # Close progress bar if it exists
        if pbar:
            pbar.close()
            
        if brand_name:
            print(f"Done! Results saved to {brand_name}_ads.csv")
        else:
            print("No data was retrieved. Please check your access token and try again.")

print("\nAll page IDs processed!")
