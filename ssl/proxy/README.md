# Info

You can find the common cert by simply [Googling](http://google.com/search?q=CTR%20Common%201%20P12&udm=14) it. You can also extract it [yourself](https://github.com/Hakky54/3ds-certificate-ripper).

To convert the P12 to an usable certificate+key, you must have [OpenSSL](https://www.openssl.org/) installed and run these commands:

```cmd
openssl pkcs12 -in ctr-common-1.p12 -out ctr-common-1.pem -clcerts -nokeys 
```

```cmd
openssl pkcs12 -in ctr-common-1.p12 -out ctr-common-1.key -nocerts -nodes
```

The password is `alpine`.

If you get error `0308010C`, run these commands instead:

```cmd
openssl pkcs12 -in ctr-common-1.p12 -out ctr-common-1.pem -clcerts -nokeys -legacy 
```

```cmd
openssl pkcs12 -in ctr-common-1.p12 -out ctr-common-1.key -nocerts -nodes -legacy
```

Ensure you have placed both files in this directory after you extracted them.
