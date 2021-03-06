#!/usr/bin/env python
# ======================================================================

import swap

import sys,getopt,datetime,os,subprocess
import numpy as np

# ======================================================================

def SWAP(argv):
    """
    NAME
        SWAP.py

    PURPOSE
        Space Warps Analysis Pipeline
        
        Read in a Space Warps classification database from a MongoDB 
        database, and analyse it.

    COMMENTS
        The SW analysis is "online" in the statistical sense: we step 
        through the classifications one by one, updating each
        classifier's agent's confusion matrix, and each subject's lens
        probability. The main reason for taking this approach is that
        it is the most logical one; secondarily, it opens up the
        possibility of performing the analysis in real time (although
        presumably not with this piece of python).

        Currently, the confusion matrices only depend on the
        classifications of training subjects. Upgrading this would be a
        nice piece of further work. Likewise, neither the Marker
        positions, the classification  durations, nor any other
        parameters are used in estimating lens probability - but they
        could be. In this version, it's LENS or NOT.

        Standard operation is to update the candidate list by making a
        new, timestamped catalog of candidates - and the
        classifications that led to them. This means we have to know
        when the last update was made - this is done by reading in a
        pickle of the last classification to be SWAPped. The final
        sample of candidates could be obtained by reading  in all
        sample pickles and taking the most up to date characterisation
        of  each - but we might as well over-write a pickle of this
        every time too. The crowd we have to always read in in its
        entirety, because they can reappear any time to update their
        confusion matrices.
        
    FLAGS
        -h            Print this message

    INPUTS
        configfile    Plain text file containing SW experiment configuration

    OUTPUTS
        stdout
        theCrowd.pickle
        theLensSampleFrom.DATE.pickle
        theClassificationBatchFrom.DATE.pickle
        theMostRecentClassification.pickle

    EXAMPLE
        
        cd workspace
        SWAP.py CFHTLS-beta-day01.config > CFHTLS-beta-day01.log

    BUGS

    AUTHORS
      This file is part of the Space Warps project, and is distributed 
      under the GPL v2 by the Space Warps Science Team.
      http://spacewarps.org/

    HISTORY
      2013-04-03 started. Marshall (Oxford)
      2013-04-17 implemented v1 "LENS or NOT" analysis. Marshall (Oxford)
    """

    # ------------------------------------------------------------------

    try:
       opts, args = getopt.getopt(argv,"h",["help"])
    except getopt.GetoptError, err:
       print str(err) # will print something like "option -a not recognized"
       print SWAP.__doc__  # will print the big comment above.
       return
    
    for o,a in opts:
       if o in ("-h", "--help"):
          print SWAP.__doc__
          return
       else:
          assert False, "unhandled option"

    # Check for setup file in array args:
    if len(args) == 1:
        configfile = args[0]
        print swap.doubledashedline
        print swap.hello
        print swap.doubledashedline
        print "SWAP: taking instructions from",configfile
    else:
        print SWAP.__doc__
        return

    # ------------------------------------------------------------------
    # Read in run configuration:
    
    tonights = swap.Configuration(configfile)
    
    practise = (tonights.parameters['dbspecies'] == 'Toy')
    if practise:
        print "SWAP: doing a dry run using a Toy database"
    else:
        print "SWAP: data will be read from the current Mongo database"
    
    agents_willing_to_learn = tonights.parameters['agents_willing_to_learn']
    if agents_willing_to_learn:
        print "SWAP: agents will update their confusion matrices as new data arrives"
    else:
        print "SWAP: agents will use current confusion matrices without updating them"
    
    vb = tonights.parameters['verbose']
    if not vb: 
        print "SWAP: only reporting minimal stdout."
    
    # From when shall we take classifications to analyze?
    if tonights.parameters['start'] == 'the_beginning':
        t1 = datetime.datetime(1978, 2, 28, 12, 0, 0, 0)
    else:
        t1 = datetime.datetime.strptime(tonights.parameters['start'], '%Y-%m-%d')
    print "SWAP: updating all subjects with classifications made since "+tonights.parameters['start']
    
    # How will we make decisions based on probability?
    thresholds = {}
    thresholds['detection'] = tonights.parameters['detection_threshold']
    thresholds['rejection'] = tonights.parameters['rejection_threshold']

    # ------------------------------------------------------------------
    # Read in, or create, a bureau of agents who will represent the 
    # volunteers:
    
    bureau = swap.read_pickle(tonights.parameters['crowdfile'],'crowd')
   
    # ------------------------------------------------------------------
    # Read in, or create, an object representing the candidate list:
    
    sample = swap.read_pickle(tonights.parameters['samplefile'],'collection')
        
    # ------------------------------------------------------------------
    # Open up database:
    
    if practise:
        
        db = swap.read_pickle(tonights.parameters['dbfile'],'database')
        
        if db is None:
            print "SWAP: making a new Toy database..."
            db = swap.ToyDB(pars=tonights.parameters)
        
        print "SWAP: database has ",db.size()," Toy classifications"
        print "SWAP: of ",db.surveysize," Toy subjects"
        print "SWAP: made by ",db.population," Toy classifiers"
        print "SWAP: where each classifier makes ",db.enthusiasm," classifications, on average"
       
    else:
    
        db = swap.MongoDB()

    # Read in a batch of classifications, made since the aforementioned 
    # start time:

    batch = db.find('since',t1)
        
    # ------------------------------------------------------------------
    
    count_max = 10000
    print "SWAP: interpreting",count_max," classifications..."
 
    count = 0
    for classification in batch:

        # Get the vitals for this classification:
        items = db.digest(classification)
        if items is None: 
            continue # Tutorial subjects fail!
        t,Name,ID,ZooID,category,kind,X,Y,location = items

        # Register new volunteers, and create an agent for each one:
        if Name not in bureau.list():  
            bureau.member[Name] = swap.Agent(Name,tonights.parameters)
        
        # Register newly-classified subjects:
        if ID not in sample.list():           
            sample.member[ID] = swap.Subject(ID,ZooID,category,kind,Y,thresholds,location)    

        # Update the subject's lens probability using input from the 
        # classifier. We send that classifier's agent to the subject
        # to do this.  
        sample.member[ID].was_described(by=bureau.member[Name],as_being=X,at_time=t)

        # Update the agent's confusion matrix, based on what it heard:
        if category == 'training' and agents_willing_to_learn:
            bureau.member[Name].heard(it_was=X,actually_it_was=Y,ignore=False)
        elif category == 'training':
            bureau.member[Name].heard(it_was=X,actually_it_was=Y,ignore=True)

        # Brag about it:
        count += 1
        if vb:
            print swap.dashedline
            print "SWAP: Subject "+ID+" was classified by "+Name
            print "SWAP: he/she said "+X+" when it was actually "+Y
            print "SWAP: their agent reckons their contribution (in bits) = ",bureau.member[Name].contribution
            print "SWAP: while estimating their PL,PD as ",bureau.member[Name].PL,bureau.member[Name].PD
            print "SWAP: and the subject's new probability as ",sample.member[ID].probability
        else:
            # Count up to 74 in dots:
            if count == 1: sys.stdout.write('SWAP: ')
            elif np.mod(count,int(count_max/73.0)) == 0: sys.stdout.write('.')
            # elif count == db.size(): sys.stdout.write('\n')
            sys.stdout.flush()
            
        if count == count_max: break
        
    sys.stdout.write('\n')
    if vb: print swap.dashedline
    print "SWAP: total no. of classifications processed: ",count

    if count == 0: 
        print "SWAP: going home early."
        return
        
    # ------------------------------------------------------------------
    
    # Set up outputs based on where we got to:
    
    # And what will we call the new files we make? Use the last 
    # classification timestamp!
    tonights.parameters['finish'] = t.strftime('%Y-%m-%d_%H-%M-%S')
    
    # Use the following directory for output lists and plots:
    trunk = tonights.parameters['survey']+'_'+tonights.parameters['finish']

    tonights.parameters['dir'] = os.getcwd()+'/'+trunk
    subprocess.call(["mkdir","-p",tonights.parameters['dir']])

    # ------------------------------------------------------------------
    # Pickle the bureau, sample, and database, if required. If we do 
    # this, its because we want to pick up from where we left off
    # (ie with SWAPSHOP) - so save the pickles in the $cwd. This is
    # taken care of in io.py.
    
    if tonights.parameters['repickle']:
    
        new_crowdfile = swap.get_new_filename(tonights.parameters,'crowd')
        print "SWAP: saving agents to "+new_crowdfile
        swap.write_pickle(bureau,new_crowdfile)

        new_samplefile = swap.get_new_filename(tonights.parameters,'collection')
        print "SWAP: saving subjects to "+new_samplefile
        swap.write_pickle(sample,new_samplefile)

        if practise:
            new_dbfile = swap.get_new_filename(tonights.parameters,'database')
            print "SWAP: saving database to "+new_dbfile
            swap.write_pickle(db,new_dbfile)

    # ------------------------------------------------------------------
    # Output list of subjects to retire, based on this batch of 
    # classifications. Note that what is needed here is the ZooID, 
    # not the subject ID:
    
    new_retirementfile = swap.get_new_filename(tonights.parameters,'retire_these')
    print "SWAP: saving newly retired subject Zooniverse IDs..."
    N = swap.write_list(sample,new_retirementfile,item='retired_subject')
    print "SWAP: "+str(N)+" lines written to "+new_retirementfile

    # Also print out lists of detections etc! These are urls of images.
    
    new_samplefile = swap.get_new_filename(tonights.parameters,'candidates')
    print "SWAP: saving new lens candidates..."
    N = swap.write_list(sample,new_samplefile,item='candidate')
    print "SWAP: "+str(N)+" lines written to "+new_samplefile
    
    # Now save the training images, for inspection: 
    new_samplefile = swap.get_new_filename(tonights.parameters,'training_true_positives')
    print "SWAP: saving new lens candidates..."
    N = swap.write_list(sample,new_samplefile,item='true_positive')
    print "SWAP: "+str(N)+" lines written to "+new_samplefile
    
    new_samplefile = swap.get_new_filename(tonights.parameters,'training_false_positives')
    print "SWAP: saving new false positives..."
    N = swap.write_list(sample,new_samplefile,item='false_positive')
    print "SWAP: "+str(N)+" lines written to "+new_samplefile
    
    new_samplefile = swap.get_new_filename(tonights.parameters,'training_false_negatives')
    print "SWAP: saving new false negatives..."
    N = swap.write_list(sample,new_samplefile,item='false_negative')
    print "SWAP: "+str(N)+" lines written to "+new_samplefile
    
    
    # ------------------------------------------------------------------
    # Make plots! Can't plot everything - uniformly sample 200 of each
    # thing (agent or subject).
    
    # Agent histories:
    
    fig1 = bureau.start_history_plot()
    pngfile = swap.get_new_filename(tonights.parameters,'histories')
    Nc = np.min([200,bureau.size()])
    print "SWAP: plotting "+str(Nc)+" agent histories in "+pngfile
    
    for Name in bureau.shortlist(Nc):
        bureau.member[Name].plot_history(fig1)
    
    bureau.finish_history_plot(fig1,pngfile)
    tonights.parameters['historiesplot'] = pngfile

    # Agent probabilities:
    
    pngfile = swap.get_new_filename(tonights.parameters,'probabilities')
    print "SWAP: plotting "+str(Nc)+" agent probabilities in "+pngfile
    bureau.plot_histogram(Nc,pngfile)        
    tonights.parameters['probabilitiesplot'] = pngfile

    # Subject probabilities:
    
    fig3 = sample.start_trajectory_plot()
    pngfile = swap.get_new_filename(tonights.parameters,'trajectories')
    Ns = np.min([500,sample.size()])
    print "SWAP: plotting "+str(Ns)+" subject trajectories in "+pngfile
    
    for ID in sample.shortlist(Ns):
        sample.member[ID].plot_trajectory(fig3)
    
    sample.finish_trajectory_plot(fig3,pngfile)
    tonights.parameters['trajectoriesplot'] = pngfile
    
    # ------------------------------------------------------------------
    # Write a PDF report:
    
    swap.write_report(tonights.parameters,bureau,sample) 
    
    # ------------------------------------------------------------------
    
    print swap.doubledashedline
    return

# ======================================================================

if __name__ == '__main__': 
    SWAP(sys.argv[1:])

# ======================================================================
