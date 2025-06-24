from scraper import health_check

def main():
    if health_check():
        print('Healthy')
    else:
        print('Failed')


if __name__ == "__main__":
    main()
