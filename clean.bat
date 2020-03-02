@echo off
del /F log/*.xml
rmdir /Q /S log
del /F peeks/*.xml
rmdir /Q /S peeks
del /F xml/*.xml
del /F xml/*.txt
rmdir /Q /S xml
del /F kp.csv
del /F *.db
rmdir /Q /S __pycache__
del /F clean.xml
