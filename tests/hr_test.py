'''
input:
4  --> lenght of list
a a c d --> list
2 --> K indices to be selected from list
'''


    #for i to L
        #for j to L

            #j>i--> no hay repos



#assuming K =2
def calc_prob_naive (n, letters,K):

    main_list = []

    for i in range (len(letters)):
        for j in range(i+1,len(letters)):
            inner_list=[letters[i],letters[j]]
            main_list.append(inner_list)


    count=0
    for inner_list in main_list:
        if "a" in inner_list:
            count+=1


    return  count/len(main_list)

def calc_prob (n, letters,K):

    prob_list=[]

    count_neg =0
    for e in letters:
        if e != 'a':
            count_neg += 1

    for i in range(K):
        prob = (count_neg-i)/(len(letters)-i)
        prob_list.append(prob)


    accum_prob=1
    for prob in prob_list:
        accum_prob*=prob


    return 1-accum_prob



if __name__ == "__main__":
    print("Starting Ex")

    print("Enter n:")
    n = int(input())
    print("Enter letters:")
    letters = input().split()
    print("Enter K:")
    K = int(input())


    print(f"Prob:{calc_prob(n,letters,K)}")




