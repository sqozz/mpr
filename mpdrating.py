# -*- coding: utf-8 -*-
from flask import Flask
from flask import request
from mpd import MPDClient
from urllib.parse import urlparse
import threading
import sqlite3
import json
import time
import hashlib

class Settings:
    __settingsFileName = ""
    __settingsString = ""
    settings = {}

    def __init__(self, settingsFileName = "settings.json"):
        self.__settingsFileName = settingsFileName
        self.reloadSettings()

    def reloadSettings(self):
        try:
            self.__settingsString = open(self.__settingsFileName).read()
            self.settings = json.loads(self.__settingsString)
        except IOError:
            print("Ooops! Something went wrong reading the settings file (\"" + self.__settingsFileName + "\")")

class RatingDatabase:
    __ratingDbConnection = None
    __dbName = ""
    __dbCursor = None
    __ratingList = list()

    def __init__(self, dbName = "ratingDatabase.sqlite"):
        self.__ratingList = list()
        self.__dbName = dbName
        try:
            self.__ratingDbConnection = sqlite3.connect(self.__dbName)
            self.__dbCursor = self.__ratingDbConnection.cursor()
            self.__dbCursor.execute("CREATE TABLE IF NOT EXISTS songs (songId INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE)")
            self.__dbCursor.execute("CREATE TABLE IF NOT EXISTS ratings (songId INTEGER, ratingDate TEXT, ip TEXT, rating INT)")
            self.__ratingDbConnection.commit()
        except DatabaseError:
            print("Ooops! Something went wrong with the database (\"" + self.__dbName + "\")")

    def addNewRating(self, newRating, songPath):
        __ip = request.remote_addr
        __currentTimestamp = int(time.time())
        __songId = 0
        try:
            self.__dbCursor.execute("INSERT OR IGNORE INTO songs (path) VALUES (:path);", {"path" : songPath})
            self.__dbCursor.execute("SELECT songId FROM songs WHERE path=:path", {"path" : songPath})
            __songId = self.__dbCursor.fetchone()[0]
            print(__songId)
            self.__dbCursor.execute("INSERT INTO ratings (songId, ratingDate, ip, rating) VALUES (:songId, :ratingDate, :ip, :rating)", { "songId" : __songId, "ratingDate" : __currentTimestamp, "ip" : __ip, "rating" : newRating})
            self.__ratingDbConnection.commit()
            return newRating
        except:
            print("Something went horribly wrong while adding a new rating to the database. Exiting now - sorry for that :(")
            return -1
            quit()

    def getRating(self, songPath):
        try:
            __currentSongId = self.__dbCursor.execute("SELECT songId FROM songs WHERE path=:path;", { "path" : songPath }).fetchone()[0]
            __ratingCount = self.__dbCursor.execute("SELECT count(*) FROM ratings WHERE songId=:songId;", { "songId" : __currentSongId }).fetchone()[0]
            __sumAllRatings = self.__dbCursor.execute("SELECT total(rating) FROM ratings WHERE songId=:songId;", { "songId" : __currentSongId }).fetchone()[0]
            if __ratingCount > 0:
                __averageRating = __sumAllRatings / __ratingCount
                return __averageRating;
            else:
                return 0
        except TypeError:
            return 0
        except:
            print("Something went horribly wrong while while calculating the rating. Exiting now - sorry for that :(")

    def genRatingList(self, maxCount):
        __allSongsDbResult = self.__dbCursor.execute("SELECT * FROM songs;")
        __allSongs = __allSongsDbResult.fetchall()
        for __singleSong in __allSongs:
            __ratingListEntryDict = dict()
            __songRatingDbResult = self.__dbCursor.execute("SELECT * FROM ratings WHERE songId=:songId;", { "songId" : __singleSong[0]})
            __songRating = self.getRating(__singleSong[1])
            __songRatingCountDbResult = self.__dbCursor.execute("SELECT count(*) FROM ratings WHERE songId=:songId", { "songId" : __singleSong[0]})
            __songRatingCount = __songRatingCountDbResult.fetchone()[0]
            __ratingListEntryDict["totalRatings"] = __songRatingCount
            __ratingListEntryDict["path"] = __singleSong[1]
            __ratingListEntryDict["averageRating"] = __songRating
            self.__ratingList.append(__ratingListEntryDict)

        self.__sortedRatingList = list()
        self.__sortedRatingList = sorted(self.__ratingList, key=lambda key: (key["averageRating"], key["totalRatings"]), reverse=True)
        return self.__sortedRatingList[:int(maxCount)]

    def close(self):
        self.__ratingDbConnection.close()

class MPDSong:
    songInfo = {"artist" : "", "title" : "", "path" : "", "rating" : ""}

    def __init__(self, path = "", artist = "", title = "", rating = 0):
        self.songInfo["artist"] = artist
        self.songInfo["title"] = title
        self.songInfo["path"] = path
        self.songInfo["rating"] = rating

    def getRating(self):
        db = RatingDatabase()
        __result = db.getRating(self.songInfo["path"])
        db.close()
        return __result

mpdRating = Flask(__name__)
@mpdRating.route("/")
def rateCurrent():
    return request.remote_addr

@mpdRating.route("/serverVersion")
def serverVersion():
    return serverVersion

@mpdRating.route("/getRatinglist", methods=['POST', 'GET'])
def getRatinglist():
    return getRatinglistJson(float(request.args["maxResults"]))

@mpdRating.route("/addToPlaylist", methods=['POST', 'GET'])
def addToPlaylist():
    songsToAdd = int(request.args["count"])
    return str(addJsonToPlaylist(json.loads(getRatinglistJson(songsToAdd))))

@mpdRating.route("/getCurrent", methods=['POST', 'GET'])
def getCurrent():
    currentSong = getCurrentSong()
    return json.dumps(currentSong.songInfo, ensure_ascii=False, sort_keys=True)

@mpdRating.route("/addNewRating", methods=['POST', 'GET'])
def addNewRating():
    db = RatingDatabase()
    currentSong = getCurrentSong()
    try:
        newRating = float(request.args["rating"])
    except ValueError:
        db.close()
        return "deniedExploit"
    if (newRating%1 == 0 and newRating > 0 and newRating < 6):
        result = db.addNewRating(newRating, currentSong.songInfo["path"])
    else:
        db.close()
        return "ratingOutOfBounds"
    db.close()
    return str(result)

def getCurrentSong():
    currentSong = MPDSong()
    mpdClient = MPDClient()
    mpdClient.timeout = 10
    mpdClient.idletimeout = None
    mpdClient.connect(settings.settings["mpdHost"], settings.settings["mpdPort"])
    mpdCurrentSong = mpdClient.currentsong()
    mpdCurrentStatus = mpdClient.status()
    if (mpdCurrentStatus.get("state", "") == "play" or mpdCurrentStatus.get("state", "") == "pause"):
        currentSong.songInfo["path"] = mpdCurrentSong.get("file","")
        isUrl = urlparse(currentSong.songInfo["path"]).scheme != ""
        currentSong.songInfo["rating"] = currentSong.getRating()
        if isUrl:
            currentSong.songInfo["artist"] = "Stream"
            currentSong.songInfo["title"] = mpdCurrentSong.get("title", "")
        else:
            currentSong.songInfo["artist"] = mpdCurrentSong.get("artist", "")
            currentSong.songInfo["title"] = mpdCurrentSong.get("title", "")

    mpdClient.close()
    mpdClient.disconnect()
    return currentSong

def addJsonToPlaylist(jsonToplist):
    mpdClient = MPDClient()
    mpdClient.timeout = 10
    mpdClient.idletimeout = None
    mpdClient.connect(settings.settings["mpdHost"], settings.settings["mpdPort"])
    totalAdded = 0
    for song in jsonToplist:
        songPath = song["path"]
        mpdClient.add(songPath)
        totalAdded += 1
    mpdClient.close()
    mpdClient.disconnect()
    return totalAdded

def getRatinglistJson(count):
    type(count)
    db = RatingDatabase()
    ratingListResult = db.genRatingList(count)
    db.close()
    del db
    return json.dumps(ratingListResult)

settings = Settings()
currentSong = MPDSong()
serverVersion = "0.1 alpha"

if __name__ == "__main__":
    mpdRating.run(host="0.0.0.0", debug=True)
