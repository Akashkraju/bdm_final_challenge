import csv
import json
import sys
import pyspark
from pyspark.sql import SparkSession

from pyproj import Transformer
from shapely.geometry import Point

if __name__ == "__main__":
    sc = pyspark.SparkContext.getOrCreate()
    spark = SparkSession(sc)

    
    rdd_1 = sc.textFile('/tmp/bdm/weekly-patterns-nyc-2019-2020').map(lambda x: next(csv.reader([x])))
    header = rdd_1.first()
    rdd_1 = rdd_1.filter(lambda row : row != header) 
    rdd_f = sc.textFile('nyc_supermarkets.csv')
    rddTask1 = rdd_1.map(lambda x: [x[0], '-'.join(x[12].split('T')[0].split('-')[:2]), '-'.join(x[13].split('T')[0].split('-')[:2]), x[18], json.loads(x[19])])

    filter_list = rdd_f.map(lambda x: x.split(',')[-2]).collect()
    rddTask1 = rddTask1.filter(lambda x: x[0] in filter_list)

    def date_list(date1,date2,cbgs):
        if date1 =='2019-03' or date2 == '2019-03':
            return [cbgs,{},{},{}]
        elif date1 =='2019-10' or date2 == '2019-10':
            return [{},cbgs,{},{}]
        elif date1 =='2020-03' or date2 == '2020-03':
            return [{},{},cbgs,{}]
        elif date1 =='2020-10' or date2 == '2020-10':
            return [{},{},{},cbgs]
        else:
            None

    def merge_by_key(a,b):
        output = [{},{},{},{}]
        for i in range(len(a)):
            output[i].update(a[i])
            output[i].update(b[i])
        return output

    rddTask2 = rddTask1.map( lambda x: (x[3],date_list(x[1],x[2],x[4]))).filter(lambda x: x[1] is not None).reduceByKey(lambda x,y: merge_by_key(x,y))

    rdd_cbg = sc.textFile('nyc_cbg_centroids.csv')
    header2 = rdd_cbg.first()
    rdd_cbg = rdd_cbg.filter(lambda row : row != header2) 
    cbg_filter = rdd_cbg.map(lambda x: x.split(',')[0]).collect()

 
    def filter_cbg(dict_in,filter_list):
        output = []
        for dict_ in dict_in:
            if dict_ == {}: output.append('')
            else:
                dict_out = []
                for item in dict_:
                    if item in filter_list:
                        dict_out.append((item,dict_[item]))
                if dict_out != []:  
                    output.append(dict_out)
                else:
                    output.append('')
        return output

    rddTask3 = rddTask2.map(lambda x: [x[0],filter_cbg(x[1],cbg_filter)])

    rdd_cbg_list = rdd_cbg.map(lambda x: [x.split(',')[0],x.split(',')[1],x.split(',')[2]]).collect()

    def cbg_transfer(input,transfer_list):
        t = Transformer.from_crs(4326, 2263)
        if type(input) == list: 
            list_out = []
            for dict_ in input:
                if dict_ == '': list_out.append('')
                else:
                    dict_out = []
                    for item1 in dict_:
                        for item2 in transfer_list:
                            if item1[0] == item2[0]:
                                dict_out.append((t.transform(item2[1],item2[2]),item1[1]))
                    list_out.append(dict_out)
            return list_out
        else:
            for item in transfer_list:
                if input == item[0]:
                    return t.transform(item[1],item[2])

    rddTask4 = rddTask3.map(lambda x: [x[0],cbg_transfer(x[0],rdd_cbg_list),cbg_transfer(x[1],rdd_cbg_list)])
    def distance(start_list,destination):
        output = []
        for item in start_list:
            if item == '':
                output.append('')
            else:
                distance_list=[]
                for start in item:
                    distance_list.append((Point(start[0][0],start[0][1]).distance(Point(destination[0],destination[1]))/5280,start[1]))
                output.append(distance_list)
        return output

    rddTask4 = rddTask4.map(lambda x: [x[0],distance(x[2],x[1])])


    def mean_dist(input):
        output = []
        for item in input:
            if item == '':
                output.append('')
            else:
                sum_ = 0
                num_ = 0
                for cuple in item:
                    sum_ += cuple[0] * cuple[1]
                    num_ += cuple[1]
                if num_ != 0:
                    output.append(str(round(sum_/num_,2)))
        return output
    rddTask5 = rddTask4.map(lambda x: [x[0],mean_dist(x[1])])

    df_out = rddTask5.map(lambda x: [str(x[0]),str(x[1][0]),str(x[1][1]) ,str(x[1][2]),str(x[1][3])])\
            .toDF(['cbg_fips', '2019-03' , '2019-10' , '2020-03' , '2020-10'])\
            .sort('cbg_fips', ascending = True)

    df_out.coalesce(1).write.options(header='true').csv(sys.argv[1])
