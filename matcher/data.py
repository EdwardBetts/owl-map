edu = ['Tag:amenity=college', 'Tag:amenity=university', 'Tag:amenity=school',
        'Tag:office=educational_institution', 'Tag:building=university']
tall = ['Key:height', 'Key:building:levels']

extra_keys = {
    'Q3914': ['Tag:building=school',
              'Tag:building=college',
              'Tag:amenity=college',
              'Tag:office=educational_institution'],  # school
    'Q322563': edu,                             # vocational school
    'Q383092': edu,                             # film school
    'Q1021290': edu,                            # music school
    'Q1244442': edu,                            # school building
    'Q1469420': edu,                            # adult education centre
    'Q2143781': edu,                            # drama school
    'Q2385804': edu,                            # educational institution
    'Q5167149': edu,                            # cooking school
    'Q7894959': edu,                            # University Technical College
    'Q47530379': edu,                           # agricultural college
    'Q38723': edu,                              # higher education institution
    'Q11303': tall,                             # skyscraper
    'Q18142': tall,                             # high-rise building
    'Q11755959': tall,                          # multi-storey building
    'Q641226': ['Tag:leisure=stadium'],         # arena
    'Q2301048': ['Tag:aeroway=helipad'],        # special airfield
    'Q622425': ['Tag:amenity=pub',
                'Tag:amenity=music_venue'],     # nightclub
    'Q187456': ['Tag:amenity=pub',
                'Tag:amenity=nightclub'],       # bar
    'Q16917': ['Tag:amenity=clinic',
               'Tag:building=clinic'],          # hospital
    'Q330284': ['Tag:amenity=market'],          # marketplace
    'Q5307737': ['Tag:amenity=pub',
                 'Tag:amenity=bar'],            # drinking establishment
    'Q875157': ['Tag:tourism=resort'],          # resort
    'Q174782': ['Tag:leisure=park',
                'Tag:highway=pedestrian',
                'Tag:foot=yes',
                'Tag:area=yes',
                'Tag:amenity=market',
                'Tag:leisure=common'],          # square
    'Q34627': ['Tag:religion=jewish'],          # synagogue
    'Q16970': ['Tag:religion=christian'],       # church
    'Q32815': ['Tag:religion=islam'],           # mosque
    'Q811979': ['Key:building'],                # architectural structure
    'Q11691': ['Key:building'],                 # stock exchange
    'Q1329623': ['Tag:amenity=arts_centre',     # cultural centre
                 'Tag:amenity=community_centre'],
    'Q856584': ['Tag:amenity=library'],         # library building
    'Q11315': ['Tag:landuse=retail'],           # shopping mall
    'Q39658032': ['Tag:landuse=retail'],        # open air shopping centre
    'Q277760': ['Tag:historic=folly',
                'Tag:historic=city_gate'],      # gatehouse
    'Q180174': ['Tag:historic=folly'],          # folly
    'Q15243209': ['Tag:leisure=park',
                  'Tag:boundary=national_park'],   # historic district
    'Q3010369': ['Tag:historic=monument'],      # opening ceremony
    'Q123705': ['Tag:place=suburb'],            # neighbourhood
    'Q256020': ['Tag:amenity=pub'],             # inn
    'Q41253': ['Tag:amenity=theatre'],          # movie theater
    'Q17350442': ['Tag:amenity=theatre'],       # venue
    'Q156362': ['Tag:amenity=winery'],          # winery
    'Q14092': ['Tag:leisure=fitness_centre',
               'Tag:leisure=sports_centre'],    # gymnasium
    'Q27686': ['Tag:tourism=hostel',            # hotel
               'Tag:tourism=guest_house',
               'Tag:building=hotel',
               'Tag:landuse=residential'],
    'Q11707': ['Tag:amenity=cafe', 'Tag:amenity=fast_food',
               'Tag:shop=deli', 'Tag:shop=bakery',
               'Key:cuisine'],                  # restaurant
    'Q2360219': ['Tag:amenity=embassy'],        # permanent mission
    'Q27995042': ['Tag:protection_title=Wilderness Area'],  # wilderness area
    'Q838948': ['Tag:historic=memorial',
                'Tag:historic=monument'],       # work of art
    'Q23413': ['Tag:place=locality'],           # castle
    'Q28045079': ['Tag:historic=archaeological_site',
                  'Tag:site_type=fortification',
                  'Tag:embankment=yes'],        # contour fort
    'Q744099': ['Tag:historic=archaeological_site',
                'Tag:site_type=fortification',
                'Tag:embankment=yes'],          # hillfort
    'Q515': ['Tag:border_type=city'],           # city
    'Q1254933': ['Tag:amenity=university'],     # astronomical observatory
    'Q1976594': ['Tag:landuse=industrial'],     # science park
    'Q190928': ['Tag:landuse=industrial'],      # shipyard
    'Q4663385': ['Tag:historic=train_station',  # former railway station
                 'Tag:railway=historic_station'],
    'Q11997323': ['Tag:emergency=lifeboat_station'],  # lifeboat station
    'Q16884952': ['Tag:castle_type=stately',
                  'Tag:building=country_house'],  # country house
    'Q1343246': ['Tag:castle_type=stately',
                 'Tag:building=country_house'],   # English country house
    'Q4919932': ['Tag:castle_type=stately'],    # stately home
    'Q1763828': ['Tag:amenity=community_centre'],  # multi-purpose hall
    'Q3469910': ['Tag:amenity=community_centre'],  # performing arts center
    'Q57660343': ['Tag:amenity=community_centre'],  # performing arts building
    'Q163740': ['Tag:amenity=community_centre',  # nonprofit organization
                'Tag:amenity=social_facility',
                'Key:social_facility'],
    'Q41176': ['Key:building:levels'],          # building
    'Q44494': ['Tag:historic=mill'],            # mill
    'Q56822897': ['Tag:historic=mill'],         # mill building
    'Q2175765': ['Tag:public_transport=stop_area'],  # tram stop
    'Q179700': ['Tag:memorial=statue',          # statue
                'Tag:memorial:type=statue',
                'Tag:historic=memorial'],
    'Q1076486': ['Tag:landuse=recreation_ground'],  # sports venue
    'Q988108': ['Tag:amenity=community_centre',  # club
                'Tag:community_centre=club_home'],
    'Q27028153': ['Tag:service=yard',
                  'Tag:landuse=railway'],       # tram depot
    'Q19563580': ['Tag:landuse=railway'],       # rail yard
    'Q134447': ['Tag:generator:source=nuclear'],  # nuclear power plant
    'Q1258086': ['Tag:leisure=park',
                 'Tag:boundary=national_park'],  # National Historic Site
    'Q32350958': ['Tag:leisure=bingo'],         # Bingo hall
    'Q53060': ['Tag:historic=gate',             # gate
               'Tag:tourism=attraction'],
    'Q3947': ['Tag:tourism=hotel',              # house
              'Tag:building=hotel',
              'Tag:tourism=guest_house'],
    'Q847017': ['Tag:leisure=sports_centre'],   # sports club
    'Q820477': ['Tag:landuse=quarry',
                'Tag:gnis:feature_type=Mine'],  # mine
    'Q77115': ['Tag:leisure=sports_centre'],    # community center
    'Q35535': ['Tag:amenity=police'],           # police
    'Q16560': ['Tag:tourism=attraction',        # palace
               'Tag:historic=yes'],
    'Q131734': ['Tag:amenity=pub',              # brewery
                'Tag:industrial=brewery'],
    'Q828909': ['Tag:landuse=commercial',
                'Tag:landuse=industrial',
                'Tag:historic=dockyard'],       # wharf
    'Q10283556': ['Tag:landuse=railway'],       # motive power depot
    'Q18674739': ['Tag:leisure=stadium'],       # event venue
    'Q20672229': ['Tag:historic=archaeological_site'],  # friary
    'Q207694': ['Tag:museum=art'],              # art museum
    'Q22698': ['Tag:leisure=dog_park',
               'Tag:amenity=market',
               'Tag:place=square',
               'Tag:leisure=common',
               'Tag:leisure=nature_reserve'],   # park
    'Q738570': ['Tag:place=suburb'],            # central business district
    'Q1133961': ['Tag:place=suburb'],           # commercial district
    'Q935277': ['Tag:gnis:ftype=Playa',
                'Tag:natural=sand'],            # salt pan
    'Q14253637': ['Tag:gnis:ftype=Playa',
                  'Tag:natural=sand'],          # dry lake
    'Q63099748': ['Tag:tourism=hotel',          # hotel building
                  'Tag:building=hotel',
                  'Tag:tourism=guest_house'],
    'Q2997369': ['Tag:leisure=park',
                 'Tag:highway=pedestrian',
                 'Tag:foot=yes',
                 'Tag:area=yes',
                 'Tag:amenity=market',
                 'Tag:leisure=common'],         # plaza
    'Q130003': ['Tag:landuse=winter_sports',    # ski resort
                'Tag:site=piste',
                'Tag:leisure=resort',
                'Tag:landuse=recreation_ground'],
    'Q4830453': ['Key:office',
                 'Tag:building=office',
                 'Tag:landuse=retail',
                 'Tag:landuse=industrial'],     # business
    'Q43229': ['Key:office',
               'Tag:building=office'],          # organization
    'Q17084016': ['Tag:office=association',
                  'Tag:office=ngo'],            # nonprofit corporation
    'Q83620': ['Key:highway'],                  # thoroughfare
    'Q33506': ['Key:building'],                 # museum
    'Q4287745': ['Tag:amenity=hospital',        # medical organization
                 'Tag:healthcare=hospital'],
    'Q4022': ['Key:waterway'],                  # stream
    'Q55659167': ['Key:waterway'],              # natural watercourse
    'Q14350': ['Key:communication:radio',
               'Tag:studio=radio',
               'Tag:amenity=studio'],           # radio station
    'Q166118': ['Tag:tourism=museum',
                'Tag:amenity=library'],         # archive
    'Q486972': ['Key:place'],                   # human settlement
    'Q42948': ['Key:barrier'],                  # wall
    'Q939644': ['Tag:historic=memorial'],       # high cross
    'Q2046310': ['Tag:historic=archaeological_site'],  # bowl barrow
    'Q2046325': ['Tag:historic=archaeological_site'],  # round barrow
    'Q472577': ['Tag:shop=mall'],  # retail park
    'Q742421': ['Tag:amenity=theatre'],         # theatrical troupe
    'Q962715': ['Key:building'],                # gas holder
    'Q52063214': ['Tag:boundary=national_park'],  # provincial park
    'Q47509284': ['Tag:landuse=brownfield'],    # assembly plant
    'Q15893266': ['Tag:landuse=brownfield'],    # former entity
    'Q43501': ['Tag:landuse=brownfield'],       # zoo
}

property_map = [
    ("P238", ["iata"], "IATA airport code"),
    ("P239", ["icao"], "ICAO airport code"),
    ("P240", ["faa", "ref"], "FAA airport code"),
    # ('P281', ['addr:postcode', 'postal_code'], 'postal code'),
    ("P296", ["ref", "ref:train", "railway:ref"], "station code"),
    ("P300", ["ISO3166-2"], "ISO 3166-2 code"),
    ("P359", ["ref:rce"], "Rijksmonument ID"),
    ("P590", ["ref:gnis", "GNISID", "gnis:id", "gnis:feature_id"], "USGS GNIS ID"),
    ("P649", ["ref:nrhp"], "NRHP reference number"),
    ("P722", ["uic_ref"], "UIC station code"),
    ("P782", ["ref"], "LAU (local administrative unit)"),
    ("P836", ["ref:gss"], "UK Government Statistical Service code"),
    ("P856", ["website", "contact:website", "url"], "website"),
    ("P882", ["nist:fips_code"], "FIPS 6-4 (US counties)"),
    ("P901", ["ref:fips"], "FIPS 10-4 (countries and regions)"),
    # A UIC id can be a IBNR, but not every IBNR is an UIC id
    ("P954", ["uic_ref"], "IBNR ID"),
    ("P981", ["ref:woonplaatscode"], "BAG code for Dutch residencies"),
    ("P1216", ["HE_ref"], "National Heritage List for England number"),
    ("P2253", ["ref:edubase"], "EDUBase URN"),
    ("P2815", ["esr:user", "ref", "ref:train"], "ESR station code"),
    ("P3425", ["ref", "ref:SIC"], "Natura 2000 site ID"),
    ("P3562", ["seamark:light:reference"], "Admiralty number"),
    (
        "P4755",
        ["ref", "ref:train", "ref:crs", "crs", "nat_ref"],
        "UK railway station code",
    ),
    ("P4803", ["ref", "ref:train"], "Amtrak station code"),
    ("P6082", ["nycdoitt:bin"], "NYC Building Identification Number"),
    ("P5086", ["ref"], "FIPS 5-2 alpha code (US states)"),
    ("P5087", ["ref:fips"], "FIPS 5-2 numeric code (US states)"),
    ("P5208", ["ref:bag"], "BAG building ID for Dutch buildings"),
]
